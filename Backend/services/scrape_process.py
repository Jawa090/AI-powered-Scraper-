"""Run a source in an owned process so a blocked scraper can be stopped safely."""
import multiprocessing
import os
import queue
import signal
import subprocess
import time

NO_DATA_TIMEOUT_SECONDS = 300


def _collect(output, stop, source, parameters, job_id, worker_id, configuration):
    if os.name != 'nt':
        os.setsid()
    from settings import settings
    settings.__dict__.update(configuration)
    from worker import JobContext
    from scrappers.controller import run
    try:
        for record in run(source, parameters, ctx=JobContext(job_id, worker_id, stop_event=stop)):
            output.put(('record', record.model_dump(mode='json')))
        output.put(('done', None))
    except Exception as exc:
        from utils.pii import mask_payload
        output.put(('error', (type(exc).__name__, str(mask_payload(str(exc))))))


def _stop(process, stop):
    stop.set()
    process.join(timeout=1)
    if process.is_alive():
        # Only this scraper's newly created process tree; an attached debugging
        # Chrome belongs to the user and is not a descendant of this process.
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process.is_alive():
            process.kill()
        process.join(timeout=2)


def run_isolated(source, parameters, ctx, *, no_data_timeout=NO_DATA_TIMEOUT_SECONDS, target=_collect):
    from settings import settings
    from services.jobs import JobCancelled, ScraperNoDataTimeout, UserWaitTimeout
    from scrappers.base import StandardRecord
    mp = multiprocessing.get_context('spawn')
    output, stop = mp.Queue(), mp.Event()
    process = mp.Process(target=target, args=(output, stop, source, parameters,
                         ctx.job_id, ctx.worker_id, dict(settings.__dict__)), daemon=False)
    process.start()
    last_record = time.monotonic()
    reason = None
    try:
        while True:
            if ctx.should_cancel():
                reason = JobCancelled('Scrape cancelled; recovered records were preserved.')
                break
            try:
                remaining = no_data_timeout - (time.monotonic() - last_record)
                kind, payload = output.get(timeout=min(.2, max(.01, remaining)))
            except queue.Empty:
                if time.monotonic() - last_record >= no_data_timeout:
                    reason = ScraperNoDataTimeout('Scraper stopped: no records received for 5 minutes.')
                    break
                if not process.is_alive():
                    raise RuntimeError('Scraper process exited without a completion signal.')
                continue
            if kind == 'record':
                last_record = time.monotonic()
                yield StandardRecord.model_validate(payload)
            elif kind == 'done':
                return
            elif kind == 'error':
                name, message = payload
                error_type = {'JobCancelled': JobCancelled, 'UserWaitTimeout': UserWaitTimeout}.get(name, RuntimeError)
                raise error_type(message)
        stop.set()
        # Drain before terminating, so an interrupted pipe write cannot leave a
        # reader blocked on a partial message after the process has been killed.
        grace_deadline = time.monotonic() + 1
        while time.monotonic() < grace_deadline:
            try:
                kind, payload = output.get(timeout=.05)
            except queue.Empty:
                if not process.is_alive():
                    break
                continue
            if kind == 'record':
                yield StandardRecord.model_validate(payload)
            elif kind in ('done', 'error'):
                break
        _stop(process, stop)
        raise reason
    finally:
        _stop(process, stop)
        output.close()
        output.cancel_join_thread()
