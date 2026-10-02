import os
import ast
import re

repo_dir = r'c:\Users\adil.zia\Desktop\Tasks\Task2\AI-powered-Scraper-\Backend\repositories'
out_db = r'c:\Users\adil.zia\Desktop\Tasks\Task2\AI-powered-Scraper-\Backend\DB_controller.py'

db_methods = []
db_methods.append('''import threading
import os
from contextlib import contextmanager
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
import logging

logger = logging.getLogger(__name__)

class DBError(Exception):
    pass

class DBController:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(DBController, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.pool = None
        self._pid = os.getpid()

    def connect(self):
        if self.pool is None or self._pid != os.getpid():
            db_url = os.getenv("DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://").replace("postgresql+asyncpg://", "postgresql://")
            self.pool = ConnectionPool(db_url, min_size=1, max_size=10, kwargs={"row_factory": dict_row})
            self._pid = os.getpid()

    def close(self):
        if self.pool:
            self.pool.close()

    @contextmanager
    def transaction(self):
        self.connect()
        with self.pool.connection() as conn:
            with conn.transaction():
                yield conn

    def _execute(self, query, params=None):
        self.connect()
        with self.pool.connection() as conn:
            return conn.execute(query, params)

    def _fetch_all(self, query, params=None):
        return self._execute(query, params).fetchall()

    def _fetch_one(self, query, params=None):
        return self._execute(query, params).fetchone()

    def _reset_for_tests(self):
        self.close()
        self.__class__._instance = None
''')

repo_files = [f for f in os.listdir(repo_dir) if f.endswith('.py') and f != '__init__.py' and f != 'base.py']

for repo_file in repo_files:
    table_name = repo_file.replace('.py', '')
    if table_name == 'agent_sessions': table_name = 'agent_session'
    filepath = os.path.join(repo_dir, repo_file)
    with open(filepath, 'r', encoding='utf-8') as f:
        code = f.read()
    try:
        tree = ast.parse(code)
    except:
        continue

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and not node.name.startswith('_'):
            func_name = f"{node.name}_{table_name}"
            args = [a.arg for a in node.args.args if a.arg != 'self']
            
            args_str = ', '.join(args)
            params_str = ', '.join(args)
            
            # Create a placeholder query
            query_str = f"SELECT * FROM {table_name}"
            if args:
                query_str += " WHERE " + " AND ".join([f"{a} = %({a})s" for a in args])
            
            method = f'''
    def {func_name}(self, {args_str}):
        """Generated method for {table_name}.{node.name}"""
        try:
            return self._fetch_all("{query_str}", {{{params_str}}})
        except Exception as e:
            logger.error(f"DB Error in {func_name}: {{e}}")
            raise DBError(e)
'''
            db_methods.append(method)

with open(out_db, 'w', encoding='utf-8') as f:
    f.write(''.join(db_methods))

db_module = '''
db = DBController()
import atexit
atexit.register(db.close)
'''
with open(out_db, 'a', encoding='utf-8') as f:
    f.write(db_module)

print("Generated DB_controller.py")
