"""Serve the application against the disposable implementation DB."""
import os, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'Backend'),str(ROOT)]
from settings import settings
from sqlalchemy.engine import make_url
name=json.loads((ROOT/'docs/audit/integration_database.json').read_text())['name']
assert name.startswith('dataops_implementation_test_')
settings.DATABASE_URL=make_url(settings.DATABASE_URL).set(database=name).render_as_string(hide_password=False)
settings.CHECKPOINT_DB_URL=make_url(settings.CHECKPOINT_DB_URL).set(database=name).render_as_string(hide_password=False)
settings.CORS_ORIGINS=['http://127.0.0.1:3010','http://localhost:3010']
settings.ENVIRONMENT='test'
import uvicorn
uvicorn.run('app:app', host='127.0.0.1',port=8010)
