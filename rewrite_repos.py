import os
import ast
import re

repo_dir = r'c:\Users\adil.zia\Desktop\Tasks\Task2\AI-powered-Scraper-\Backend\repositories'

repo_files = [f for f in os.listdir(repo_dir) if f.endswith('.py') and f != '__init__.py' and f != 'base.py']

for repo_file in repo_files:
    table_name = repo_file.replace('.py', '')
    if table_name == 'agent_sessions': table_name = 'agent_session'
    filepath = os.path.join(repo_dir, repo_file)
    with open(filepath, 'r', encoding='utf-8') as f:
        code = f.read()
    
    # We will do a basic string replacement approach to replace method bodies.
    # This is a heuristic and might break formatting, but demonstrates the refactor.
    try:
        tree = ast.parse(code)
    except:
        continue
    
    lines = code.split('\n')
    new_lines = []
    
    # Prepend the DBController import
    new_lines.append("from DB_controller import db")
    
    skip_lines = 0
    in_class = False
    
    for i, line in enumerate(lines):
        if skip_lines > 0:
            skip_lines -= 1
            continue
            
        if line.startswith("class "):
            in_class = True
            new_lines.append(line)
            # Find methods and replace their bodies
            continue
            
        if line.strip().startswith("def ") and in_class and not line.strip().startswith("def _"):
            # Extract method name
            m = re.search(r'def (\w+)\(', line)
            if m:
                func_name = m.group(1)
                new_lines.append(line)
                
                # Find arguments
                args_str = line[line.find('(')+1 : line.find(')')]
                args = [a.split(':')[0].strip() for a in args_str.split(',') if a.strip() and a.split(':')[0].strip() not in ('self', '*')]
                
                db_func = f"{func_name}_{table_name}"
                args_passed = ', '.join([a for a in args if '=' not in a])
                
                indent = line[:len(line) - len(line.lstrip())]
                body_indent = indent + "    "
                
                new_lines.append(f"{body_indent}return db.{db_func}({args_passed})")
                
                # skip until next def or dedent
                j = i + 1
                while j < len(lines):
                    next_line = lines[j]
                    if not next_line.strip():
                        j += 1
                        continue
                    if not next_line.startswith(body_indent):
                        break
                    j += 1
                
                skip_lines = j - i - 1
                continue
        
        # Remove SQLAlchemy imports
        if 'sqlalchemy' in line or 'Session' in line:
            continue
            
        new_lines.append(line)
        
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines))

print("Repositories refactored!")
