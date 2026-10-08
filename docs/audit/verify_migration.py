"""Fresh migration and rollback/reapply, confined to a new disposable DB."""
import json, sys, uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'Backend'), str(ROOT)]
from settings import settings
import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url
url = make_url(settings.DATABASE_URL)
name = 'dataops_migration_test_' + uuid.uuid4().hex[:10]
assert name.startswith('dataops_migration_test_')
with psycopg.connect(url.set(drivername='postgresql', database='postgres').render_as_string(hide_password=False),autocommit=True) as conn:
    conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
settings.DATABASE_URL = url.set(database=name).render_as_string(hide_password=False)
from alembic.config import Config
from alembic import command
cfg=Config(str(ROOT/'Backend/alembic.ini'));cfg.set_main_option('script_location',str(ROOT/'Backend/migrations'))
command.upgrade(cfg,'9f8b7c6a5d4e')
dsn=url.set(drivername='postgresql',database=name).render_as_string(hide_password=False)
with psycopg.connect(dsn) as conn:
    conn.execute("INSERT INTO leads (id,title,source_code,status,identity_key,lead_metadata) VALUES ('legacy-migration','Roofing bid','DASNY','New','legacy-migration-key',%s)", (json.dumps({'category':'Roofing','city':'New York','us_state':'ny'}),))
command.upgrade(cfg,'head')
with psycopg.connect(dsn) as conn:
    row=conn.execute("SELECT record_kind,category,city,us_state FROM leads WHERE id='legacy-migration'").fetchone()
    assert row == ('opportunity','Roofing','New York','NY'), row
    count=conn.execute('SELECT count(*) FROM leads').fetchone()[0]
command.downgrade(cfg,'9f8b7c6a5d4e')
command.upgrade(cfg,'head')
with psycopg.connect(dsn) as conn:
    assert conn.execute('SELECT count(*) FROM leads').fetchone()[0] == count
    assert conn.execute("SELECT record_kind,us_state FROM leads WHERE id='legacy-migration'").fetchone() == ('opportunity','NY')
    head=conn.execute('SELECT version_num FROM alembic_version').fetchone()[0]
report={'freshMigration':True,'rollbackReapply':True,'legacyBackfill':True,'rowsPreserved':True,'revision':head}
(ROOT/'docs/audit/migration_verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report),flush=True)
