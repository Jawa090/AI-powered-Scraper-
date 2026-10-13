import os
import re

models = [
    'Department', 'User', 'Agent', 'AgentSession', 'AgentMessage',
    'Requirement', 'Query', 'Source', 'ScrapeRun', 'Job',
    'Dataset', 'DatasetRecord', 'Organization', 'Contact', 'Email',
    'Phone', 'Location', 'Lead', 'AgentAction', 'QueryResult',
    'LeadSource', 'SessionEvent'
]

directories = ['Backend', 'Database', 'scripts']
usage_counts = {m: 0 for m in models}

for d in directories:
    for root, _, files in os.walk(d):
        if 'models' in root and 'Database' in root:
            continue
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    for m in models:
                        # Find whole word matches for the model name
                        if re.search(r'\b' + m + r'\b', content):
                            usage_counts[m] += 1

print('Model Usage Counts (outside Database/models):')
for m, count in sorted(usage_counts.items(), key=lambda x: x[1]):
    print(f'{m}: {count}')
