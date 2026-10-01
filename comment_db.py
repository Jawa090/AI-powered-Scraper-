import os
import re

search_dirs = [r'c:\Users\adil.zia\Desktop\Tasks\Task2\AI-powered-Scraper-\Backend']
pattern = re.compile(r'(create_engine|sessionmaker|from sqlalchemy|\.execute\(|text\()')

for d in search_dirs:
    for root, dirs, files in os.walk(d):
        for f in files:
            if f.endswith('.py') and 'DB_controller' not in f and 'models' not in root and 'migrations' not in root and 'repositories' not in root and 'services' not in root:
                filepath = os.path.join(root, f)
                with open(filepath, 'r', encoding='utf-8') as file:
                    content = file.read()
                
                if pattern.search(content):
                    lines = content.split('\n')
                    new_lines = []
                    for line in lines:
                        if 'from database.connection' in line:
                            new_lines.append('# ' + line)
                        elif 'import sqlalchemy' in line or 'from sqlalchemy' in line:
                            new_lines.append('# ' + line)
                        elif 'SessionLocal()' in line or 'db.execute' in line or 'session.execute' in line or 'engine.execute' in line or 'conn.execute' in line or 'cur.execute' in line:
                            new_lines.append('# ' + line)
                        else:
                            new_lines.append(line)
                    with open(filepath, 'w', encoding='utf-8') as file:
                        file.write('\n'.join(new_lines))

print("Commented out remaining raw DB usages.")
