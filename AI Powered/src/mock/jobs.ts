import { Job } from '../types';

export const MOCK_JOBS: Job[] = [
  {
    "id": "job-1789122766-666d",
    "name": "JWiz Commercial & Services Directory Scraper Run",
    "type": "Commercial B2B Directory",
    "scriptId": "jwiz",
    "scriptName": "JWiz Commercial & Services Directory Scraper",
    "departmentId": "dept-sales-1",
    "departmentName": "Sales & Email Outreach",
    "progress": 100,
    "status": "Completed",
    "currentStep": "Dataset Created Successfully",
    "startedAt": "2026-09-11 03:32 PM",
    "duration": "00:03",
    "recordsFound": 5,
    "verifiedCount": 3,
    "duplicatesCount": 1,
    "errorsCount": 0,
    "totalTarget": 5,
    "datasetId": "ds-df0b49",
    "parameters": {
      "limit": 5,
      "location": "new-york",
      "keyword": "plumber"
    },
    "logs": [
      {
        "timestamp": "15:32:46",
        "level": "info",
        "message": "Job queued for script 'JWiz Commercial & Services Directory Scraper'. Target: 5 records."
      },
      {
        "timestamp": "15:32:46",
        "level": "info",
        "message": "Engine environment launched successfully."
      },
      {
        "timestamp": "15:32:47",
        "level": "info",
        "message": "Searching JWiz directory for category: plumber, location: new-york"
      },
      {
        "timestamp": "15:32:49",
        "level": "info",
        "message": "Parsing HTML card structures and company profiles..."
      },
      {
        "timestamp": "15:32:50",
        "level": "info",
        "message": "Extraction complete. 5 verified records added to dataset 'JWiz Commercial & Services Directory Scraper (Sep 11, 15:32)'."
      }
    ]
  },
  {
    "id": "job-bonfire-live",
    "name": "Dallas City Hall Bonfire Portal Run",
    "type": "Government & Municipal Bids",
    "scriptId": "bonfire",
    "scriptName": "Dallas City Hall Bonfire Scraper",
    "departmentId": "dept-sales-1",
    "departmentName": "Procurement & Bids",
    "progress": 100,
    "status": "Completed",
    "currentStep": "Dataset Created Successfully",
    "startedAt": "2026-09-11 03:31 PM",
    "duration": "00:18",
    "recordsFound": 22,
    "verifiedCount": 22,
    "duplicatesCount": 0,
    "errorsCount": 0,
    "totalTarget": 22,
    "datasetId": "ds-dallas-bonfire",
    "logs": [
      {
        "timestamp": "15:31:05",
        "level": "info",
        "message": "Dallas Bonfire portal connected (dallascityhall.bonfirehub.com)"
      },
      {
        "timestamp": "15:31:12",
        "level": "info",
        "message": "22 open procurement opportunities discovered in active table."
      },
      {
        "timestamp": "15:31:23",
        "level": "info",
        "message": "Extracted Ref #, Title, Close Date, and buyer URL specifications."
      },
      {
        "timestamp": "15:31:24",
        "level": "info",
        "message": "Dataset created: 22 records saved to ds-dallas-bonfire."
      }
    ]
  },
  {
    "id": "job-dasny-live",
    "name": "DASNY RFP Opportunities Run",
    "type": "State Authority RFPs",
    "scriptId": "dasny",
    "scriptName": "DASNY RFP & Bid Opportunities Scraper",
    "departmentId": "dept-sales-1",
    "departmentName": "State Contracts & RFPs",
    "progress": 100,
    "status": "Completed",
    "currentStep": "Dataset Created Successfully",
    "startedAt": "2026-09-11 02:15 PM",
    "duration": "00:25",
    "recordsFound": 6,
    "verifiedCount": 6,
    "duplicatesCount": 0,
    "errorsCount": 0,
    "totalTarget": 10,
    "datasetId": "ds-dasny-rfps",
    "logs": [
      {
        "timestamp": "14:15:02",
        "level": "info",
        "message": "DASNY portal connected (dasny.org/opportunities/rfps-bids)"
      },
      {
        "timestamp": "14:15:15",
        "level": "info",
        "message": "Discovered active architectural and construction RFPs."
      },
      {
        "timestamp": "14:15:25",
        "level": "info",
        "message": "Dataset created: 6 verified opportunities saved to ds-dasny-rfps."
      }
    ]
  },
  {
    "id": "job-nyscr-live",
    "name": "NYSCR State Contracts Run",
    "type": "Statewide Contracts",
    "scriptId": "nyscr",
    "scriptName": "NYSCR State Contract Reporter Scraper",
    "departmentId": "dept-sales-1",
    "departmentName": "Public Sector Procurement",
    "progress": 100,
    "status": "Completed",
    "currentStep": "Dataset Created Successfully",
    "startedAt": "2026-09-11 01:40 PM",
    "duration": "00:21",
    "recordsFound": 5,
    "verifiedCount": 5,
    "duplicatesCount": 0,
    "errorsCount": 0,
    "totalTarget": 10,
    "datasetId": "ds-nyscr-contracts",
    "logs": [
      {
        "timestamp": "13:40:01",
        "level": "info",
        "message": "NYSCR adsOpen portal queried."
      },
      {
        "timestamp": "13:40:12",
        "level": "info",
        "message": "Discovered state agency contracts and issuing organizations."
      },
      {
        "timestamp": "13:40:21",
        "level": "info",
        "message": "Dataset created: 5 contracts saved to ds-nyscr-contracts."
      }
    ]
  },
  {
    "id": "job-1789124919-cc03",
    "name": "Dallas City Hall Bonfire Scraper Run",
    "type": "Government & Municipal Bids",
    "scriptId": "bonfire",
    "scriptName": "Dallas City Hall Bonfire Scraper",
    "departmentId": "dept-sales-1",
    "departmentName": "Procurement & Bids",
    "progress": 100,
    "status": "Completed",
    "currentStep": "Dataset Created Successfully",
    "startedAt": "2026-09-11 04:08 PM",
    "duration": "00:12",
    "recordsFound": 20,
    "verifiedCount": 18,
    "duplicatesCount": 1,
    "errorsCount": 0,
    "totalTarget": 20,
    "datasetId": "ds-9db6a2",
    "parameters": {
      "limit": 20,
      "location": "new-york",
      "keyword": "contractor"
    },
    "logs": [
      {
        "timestamp": "16:08:39",
        "level": "info",
        "message": "Job queued for script 'Dallas City Hall Bonfire Scraper'. Target: 20 records."
      },
      {
        "timestamp": "16:08:39",
        "level": "info",
        "message": "Engine environment launched successfully."
      },
      {
        "timestamp": "16:08:39",
        "level": "info",
        "message": "Navigating to City of Dallas Bonfire portal..."
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Discovered 22 open opportunities on Dallas City Hall portal."
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Extracted [BG26-00030710] Street Sweeping Services (Closes: Sep 11th 2026, 1:00 PM CDT)"
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Extracted [CIZ-DWU-CONTRACT NO. 12] 2027 PAVEMENT REPAIRS PAVING CONTRACT NO. 12 (Closes: Sep 11th 2026, 1:00 PM CDT)"
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Extracted [BYZ26-00030828] Temporary Stagehand and Tech Labor (Closes: Sep 11th 2026, 1:00 PM CDT)"
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Extracted [BD26-00030929] Flags - USA, State of Texas, City of Dallas,  (Closes: Sep 11th 2026, 1:00 PM CDT)"
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Extracted [BT26-00030640] Fire Extinguishers and Sprinkler Systems (Closes: Sep 11th 2026, 1:00 PM CDT)"
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Extracted [CIZ26-TPW-4006] Engineering Services for the Union Pacific Ra (Closes: Sep 11th 2026, 1:00 PM CDT)"
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Extracted [CIZ26-PKR-3232] Dallas Park and Recreation Department - Audel (Closes: Sep 11th 2026, 1:00 PM CDT)"
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Extracted [HCE-2026-00030960] EARLY CHILDHOOLD AND OUT-OF-SCHOOL TIME SERVI (Closes: Sep 11th 2026, 2:00 PM CDT)"
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Extracted [IFS - AVI B2100005] *219244 Purchase of Shaft Assembly (Closes: Sep 16th 2026, 1:00 PM CDT)"
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Extracted [CIZ26-PKR-29584] Crawford Memorial Park Phase I Improvements (Closes: Sep 18th 2026, 1:00 PM CDT)"
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Extracted [CIZ-DWU-26 309/310E] Small and Medium Sized Water and Wastewater M (Closes: Sep 18th 2026, 1:00 PM CDT)"
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Extracted [BG26-00030762] Fire Hydrant, Parts, Accessories and Flushing (Closes: Sep 18th 2026, 1:00 PM CDT)"
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Extracted [BT26-00030659] Barricading and Traffic Control Services (Closes: Sep 18th 2026, 1:00 PM CDT)"
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Extracted [BU26-00031034] Vendor Compliance Monitoring and Site Managem (Closes: Sep 18th 2026, 1:00 PM CDT)"
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Extracted [BU26-00030935] Electrical Switchgear Repair Services (Closes: Sep 18th 2026, 1:00 PM CDT)"
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Extracted [BG26-00031088] Workday RFI (Closes: Sep 25th 2026, 1:00 PM CDT)"
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Extracted [CIZ-DWU 26 165 166] WATER AND WASTEWATER MAIN REPLACEMENTS AT VAR (Closes: Sep 25th 2026, 1:00 PM CDT)"
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Extracted [CIZ26-OBP-30859] Request for Competitive Sealed Proposals for  (Closes: Sep 25th 2026, 1:00 PM CDT)"
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Extracted [CIZ26-TPW-4000] SL 12 (Walton Walker Blvd) at Country Creek D (Closes: Sep 25th 2026, 1:00 PM CDT)"
      },
      {
        "timestamp": "16:08:49",
        "level": "info",
        "message": "Extracted [CIZ-DWU 26 227] EMERGENCY AND ROUTINE WATER SYSTEM REPAIRS AN (Closes: Oct 2nd 2026, 1:00 PM CDT)"
      },
      {
        "timestamp": "16:08:51",
        "level": "info",
        "message": "Extraction complete. 20 verified records added to dataset 'Dallas City Hall Bonfire Scraper (Sep 11, 16:08)'."
      }
    ]
  }
];
