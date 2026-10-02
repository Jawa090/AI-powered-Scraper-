import os, sys
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath('app.py')))
sys.path.insert(0, PROJECT_ROOT)

from Database import db
try:
    print('Connecting...')
    db.connect()
    # execute returns a result, we just test if it crashes or not
    with db.session as session:
        result = session.execute('SELECT 1')
        print('Connected successfully! SELECT 1 result:', list(result))
except Exception as e:
    import traceback
    traceback.print_exc()
