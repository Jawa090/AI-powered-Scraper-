"""Inspect recent configured chat failures without exporting delivered contact data."""
import sys
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'Backend'), str(ROOT)]
from Database.controller import session_scope
from Database.models.query import Query
from sqlalchemy import select
from agents.graph.checkpointer import setup_checkpointer
from agents.graph.graph import get_compiled_graph
setup_checkpointer()
with session_scope() as db:
    rows = db.scalars(select(Query).where(Query.status.in_(['failed', 'llm_unavailable']))
                      .order_by(Query.created_at.desc()).limit(5)).all()
for row in rows:
    snap = get_compiled_graph().get_state({'configurable': {'thread_id': row.session_id}})
    print(json.dumps({'queryId': row.id, 'created': str(row.created_at), 'text': row.query_text,
        'status': row.status, 'next': snap.next, 'taskErrors': [str(task.error) for task in snap.tasks if task.error],
        'slots': snap.values.get('slots'),
        'missing': snap.values.get('missing_requirements'),
        'messages': [{'type': getattr(m, 'type', ''), 'toolCalls': getattr(m, 'tool_calls', None),
                      'content': str(m.content)[:350] if getattr(m, 'type', '') != 'tool' else '(tool result omitted)'}
                     for m in snap.values.get('messages', [])[-3:]]}, default=str), flush=True)
