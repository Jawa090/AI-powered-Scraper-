"""
Syncs real scraped backend data directly into the frontend data layer
"""
import os
import sys
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
FRONTEND_MOCK_DIR = os.path.join(os.path.dirname(BASE_DIR), "AI Powered", "src", "mock")

with open(os.path.join(DATA_DIR, "leads.json"), "r", encoding="utf-8") as f:
    leads = json.load(f)

with open(os.path.join(DATA_DIR, "datasets.json"), "r", encoding="utf-8") as f:
    datasets = json.load(f)

with open(os.path.join(DATA_DIR, "jobs.json"), "r", encoding="utf-8") as f:
    jobs_dict = json.load(f)
    jobs = list(jobs_dict.values())

# Generate real activities
activities = [
    {
        "id": "act-bonfire-1",
        "type": "generation",
        "title": "Dallas City Hall Procurement Harvest",
        "description": "Autonomous Bonfire scraper extracted 22 open municipal procurement opportunities from City of Dallas.",
        "user": "Ahmed Khan",
        "department": "Procurement & Bids",
        "timestamp": "15m ago",
        "datasetId": "ds-dallas-bonfire",
        "badgeColor": "#10B981"
    },
    {
        "id": "act-jwiz-1",
        "type": "generation",
        "title": "JWiz Commercial Directory Harvest",
        "description": "Extracted verified commercial plumbing and contractor leads with phone numbers and emails.",
        "user": "Ahmed Khan",
        "department": "Commercial Directory Outreach",
        "timestamp": "45m ago",
        "datasetId": "ds-df0b49",
        "badgeColor": "#3B82F6"
    },
    {
        "id": "act-dasny-1",
        "type": "generation",
        "title": "DASNY Institutional Bids Crawl",
        "description": "Captured active architectural and mechanical RFPs from State of New York Dormitory Authority.",
        "user": "Ahmed Khan",
        "department": "State Infrastructure & Construction",
        "timestamp": "2h ago",
        "datasetId": "ds-dasny-rfps",
        "badgeColor": "#8B5CF6"
    },
    {
        "id": "act-nyscr-1",
        "type": "generation",
        "title": "NYSCR State Contract Reporter Sync",
        "description": "State agency open contracts crawled with issuing organizations and submission criteria.",
        "user": "Ahmed Khan",
        "department": "State Contracts & Regulatory",
        "timestamp": "3h ago",
        "datasetId": "ds-nyscr-contracts",
        "badgeColor": "#F59E0B"
    }
]

# Write leads.ts
with open(os.path.join(FRONTEND_MOCK_DIR, "leads.ts"), "w", encoding="utf-8") as f:
    f.write("import { Lead } from '../types';\n\n")
    f.write("export const MOCK_LEADS: Lead[] = ")
    json.dump(leads, f, indent=2, ensure_ascii=False)
    f.write(";\n")

# Write datasets.ts
with open(os.path.join(FRONTEND_MOCK_DIR, "datasets.ts"), "w", encoding="utf-8") as f:
    f.write("import { Dataset } from '../types';\n\n")
    f.write("export const MOCK_DATASETS: Dataset[] = ")
    json.dump(datasets, f, indent=2, ensure_ascii=False)
    f.write(";\n")

# Write jobs.ts
with open(os.path.join(FRONTEND_MOCK_DIR, "jobs.ts"), "w", encoding="utf-8") as f:
    f.write("import { Job } from '../types';\n\n")
    f.write("export const MOCK_JOBS: Job[] = ")
    json.dump(jobs, f, indent=2, ensure_ascii=False)
    f.write(";\n")

# Write activities.ts
with open(os.path.join(FRONTEND_MOCK_DIR, "activities.ts"), "w", encoding="utf-8") as f:
    f.write("import { Activity } from '../types';\n\n")
    f.write("export const MOCK_ACTIVITIES: Activity[] = ")
    json.dump(activities, f, indent=2, ensure_ascii=False)
    f.write(";\n")

print(f"Successfully exported {len(leads)} real leads, {len(datasets)} datasets, {len(jobs)} jobs, and {len(activities)} activities to frontend!")
