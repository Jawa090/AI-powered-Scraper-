import os
import sys

# Ensure project root is in path
PROJECT_ROOT = r"c:\Users\adil.zia\Desktop\Tasks\Task2\AI-powered-Scraper-"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from Database import db
from Database.models.query import Query

try:
    print(Query.jobs)
except Exception as e:
    print(f"Error: {e}")
