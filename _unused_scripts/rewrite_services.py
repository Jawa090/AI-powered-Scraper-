import os
import ast
import re

services_dir = r'c:\Users\adil.zia\Desktop\Tasks\Task2\AI-powered-Scraper-\Backend\services'
service_files = [f for f in os.listdir(services_dir) if f.endswith('.py') and f != '__init__.py']

for sf in service_files:
    filepath = os.path.join(services_dir, sf)
    with open(filepath, 'r', encoding='utf-8') as f:
        code = f.read()
    
    lines = code.split('\n')
    new_lines = []
    for line in lines:
        if 'sqlalchemy' in line or 'Session' in line and 'import' in line:
            continue
        # Remove session argument from __init__
        line = re.sub(r',\s*session:\s*Session', '', line)
        line = re.sub(r'session:\s*Session\s*,?', '', line)
        line = re.sub(r'self\.session\s*=\s*session', '', line)
        new_lines.append(line)
        
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines))

print("Services refactored!")
