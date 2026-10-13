"""Real process termination and inactivity timer resets without live websites."""
import multiprocessing
import os
import time
from types import SimpleNamespace
import pytest
from services.scrape_process import run_isolated, NO_DATA_TIMEOUT_SECONDS
from services.jobs import ScraperNoDataTimeout, JobCancelled


def blocked_source(output, stop, source, params, jid, wid, configuration):
    output.put(('record', {'source_code':'jwiz', 'record_kind':'company', 'external_id':'blocked-test',
                          'organization_name':'Blocked test', 'extra':{'childPid':os.getpid()}}))
    while True:
        time.sleep(20)


def reporting_source(output, stop, source, params, jid, wid, configuration):
    for index in range(4):
        output.put(('record', {'source_code':'jwiz', 'record_kind':'company', 'external_id':str(index),
                              'organization_name':'Reporting test', 'extra':{'childPid':os.getpid()}}))
        time.sleep(.15)
    output.put(('done', None))


def test_five_minute_constant_and_hard_stop_of_blocked_owned_process():
    assert NO_DATA_TIMEOUT_SECONDS == 300
    ctx = SimpleNamespace(job_id='test', worker_id='test', should_cancel=lambda:False)
    stream = run_isolated('jwiz', {}, ctx, no_data_timeout=5, target=blocked_source)
    record = next(stream)
    pid = record.extra['childPid']
    started = time.monotonic()
    with pytest.raises(ScraperNoDataTimeout, match='5 minutes'):
        next(stream)
    assert time.monotonic() - started < 10
    assert pid not in [child.pid for child in multiprocessing.active_children()]


def test_clear_cancels_blocked_process_and_preserves_already_received_record():
    cancelled = [False]
    ctx = SimpleNamespace(job_id='test', worker_id='test', should_cancel=lambda:cancelled[0])
    stream = run_isolated('jwiz', {}, ctx, no_data_timeout=10, target=blocked_source)
    record = next(stream)
    cancelled[0] = True
    with pytest.raises(JobCancelled):
        next(stream)
    assert record.external_id == 'blocked-test'
    assert record.extra['childPid'] not in [child.pid for child in multiprocessing.active_children()]


def test_receiving_records_resets_inactivity_watchdog(monkeypatch):
    # A thread-backed process double isolates the timing rule from Windows startup.
    import queue, threading
    class Process:
        def __init__(self, target, args, **kwargs):
            self.thread = threading.Thread(target=target, args=args)
        def start(self): self.thread.start()
        def join(self, timeout=None): self.thread.join(timeout)
        def is_alive(self): return self.thread.is_alive()
    class Queue(queue.Queue):
        def close(self): pass
        def cancel_join_thread(self): pass
    mp = SimpleNamespace(Queue=Queue, Event=threading.Event, Process=Process)
    monkeypatch.setattr(multiprocessing, 'get_context', lambda *_:mp)
    ctx = SimpleNamespace(job_id='test', worker_id='test', should_cancel=lambda:False)
    started = time.monotonic()
    rows = list(run_isolated('jwiz', {}, ctx, no_data_timeout=.3, target=reporting_source))
    assert len(rows) == 4 and time.monotonic()-started > .3


@pytest.mark.parametrize("source", ["bonfire", "dasny", "jwiz", "nyscr"])
def test_run_isolated_all_four_scrapers_fixture_mode(source, monkeypatch):
    from settings import settings
    monkeypatch.setattr(settings, "SCRAPER_MODE", "fixture")
    monkeypatch.setattr(settings, "ENVIRONMENT", "test")
    ctx = SimpleNamespace(job_id=f"test-{source}", worker_id="test-worker", should_cancel=lambda: False)
    params = {"limit": 2, **({"us_state": "NY"} if source == "jwiz" else {})}
    rows = list(run_isolated(source, params, ctx, no_data_timeout=30))
    assert len(rows) == 2
    for r in rows:
        assert r.source_code == source
        assert r.record_kind in ("opportunity", "company")
