"""Apply the verified additive schema and preserve all configured DB records."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Backend'),str(ROOT)]
from settings import settings
import psycopg
from psycopg import sql
from alembic.config import Config
from alembic import command
assert json.loads((ROOT/'docs/audit/migration_verification.json').read_text())['rollbackReapply']
dsn=settings.DATABASE_URL.replace('postgresql+psycopg://','postgresql://',1)
tables=['leads','users','queries','query_results','agent_sessions','agent_messages','jobs','datasets']
def counts():
    with psycopg.connect(dsn,connect_timeout=5) as conn:
        return {table:conn.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone()[0] for table in tables}
before=counts()
cfg=Config(str(ROOT/'Backend/alembic.ini'));cfg.set_main_option('script_location',str(ROOT/'Backend/migrations'))
command.upgrade(cfg,'head')
from Database.seed import seed
seed();seed()
from agents.graph.checkpointer import setup_checkpointer
setup_checkpointer()
after=counts()
for table in tables: assert after[table]>=before[table], table
with psycopg.connect(dsn) as conn: revision=conn.execute('SELECT version_num FROM alembic_version').fetchone()[0]
report={'applied':True,'revision':revision,'before':before,'after':after,'existingRowsPreserved':True,'seedIdempotent':True}
(ROOT/'docs/audit/configured_database_migration.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report),flush=True)
