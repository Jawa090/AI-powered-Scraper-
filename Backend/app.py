"""
FastAPI Server for DataOps Autonomous Intelligence Platform
Wraps 4 scraping engines, manages background job queues, provides REST APIs,
and connects seamlessly with the frontend AI Agent Bot.
"""

import os
import sys
import json
import time
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from scraper_manager import scraper_manager, SCRIPTS_REGISTRY

app = FastAPI(
    title="DataOps AI Extraction Backend",
    description="FastAPI service connecting DASNY, NYSCR, JWiz, and Dallas Bonfire scrapers with the AI Agent.",
    version="1.0.0",
)

# CORS configuration for Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class RunScriptRequest(BaseModel):
    scriptId: str = Field(..., description="ID of script to run: bonfire, dasny, jwiz, or nyscr")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Custom parameters (limit, keyword, location, etc.)")


class BotChatRequest(BaseModel):
    sessionId: str
    message: str
    history: Optional[List[Dict[str, Any]]] = None
    currentRequirement: Optional[Dict[str, Any]] = None


class BotConfirmRequest(BaseModel):
    sessionId: str
    requirement: Dict[str, Any]
    preferredScriptId: Optional[str] = None


# ---------------------------------------------------------------------------
# Health & Status
# ---------------------------------------------------------------------------
@app.get("/")
@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "service": "DataOps AI Backend",
        "timestamp": time.time(),
        "registeredScripts": len(SCRIPTS_REGISTRY),
    }


# ---------------------------------------------------------------------------
# Script Management Endpoints
# ---------------------------------------------------------------------------
@app.get("/api/scripts")
def list_scripts():
    """Returns all 4 registered scraping scripts with live metadata."""
    return {"scripts": scraper_manager.get_scripts()}


@app.get("/api/scripts/{script_id}")
def get_script_detail(script_id: str):
    script = scraper_manager.get_script(script_id)
    if not script:
        raise HTTPException(status_code=404, detail=f"Script '{script_id}' not found.")
    return {"script": script}


@app.post("/api/scripts/run")
def run_script(req: RunScriptRequest):
    """Triggers any of the 4 scripts in the background and returns a jobId."""
    script = scraper_manager.get_script(req.scriptId)
    if not script:
        raise HTTPException(status_code=404, detail=f"Unknown script '{req.scriptId}'")

    job_id = scraper_manager.create_job(req.scriptId, req.parameters)
    return {
        "success": True,
        "message": f"Execution started for {script['name']}",
        "jobId": job_id,
        "scriptId": req.scriptId,
    }


# ---------------------------------------------------------------------------
# Job Execution & Progress Tracking
# ---------------------------------------------------------------------------
@app.get("/api/jobs")
def list_jobs():
    """Returns list of all scraper jobs (both active and completed)."""
    return {"jobs": scraper_manager.get_jobs()}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    """Returns real-time status, progress, records count, and logs for a job."""
    job = scraper_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return {"job": job}


# ---------------------------------------------------------------------------
# Leads and Datasets
# ---------------------------------------------------------------------------
@app.get("/api/datasets")
def list_datasets():
    """Returns datasets created from scraper runs."""
    return {"datasets": scraper_manager.get_datasets()}


@app.get("/api/leads")
def list_leads(datasetId: Optional[str] = Query(None), query: Optional[str] = Query(None)):
    """Returns leads and opportunities extracted by scrapers."""
    leads = scraper_manager.get_leads(dataset_id=datasetId, query=query)
    return {"leads": leads, "total": len(leads)}


# ---------------------------------------------------------------------------
# AI Agent Bot Integration Endpoints
# ---------------------------------------------------------------------------
@app.post("/api/bot/chat")
def bot_chat(req: BotChatRequest):
    """
    Intelligent Multi-Turn Cross-Questioning Bot Endpoint:
    Clearly presents the 4 scraper engines by name, conducts an interactive cross-questioning interview
    to pinpoint the user's exact requirements, and prepares targeted lead extractions.
    """
    text = req.message.strip()
    lower = text.lower()
    req_data = req.currentRequirement or {
        "industry": "Not specified",
        "location": "Not specified",
        "companySize": "Not specified",
        "decisionMakers": [],
        "quantity": 0,
        "completionPercentage": 10,
        "status": "collecting",
    }

    current_script = req_data.get("selectedScript")
    reply_text = ""
    suggestions: List[str] = []
    recommended_script = current_script

    # ─────────────────────────────────────────────────────────────
    # 1. SCRAPER ENGINE SELECTION DETECTION (By Name)
    # ─────────────────────────────────────────────────────────────
    is_bonfire = any(k in lower for k in ["dallas", "bonfire", "city hall", "texas bid", "municipal"])
    is_dasny = any(k in lower for k in ["dasny", "dormitory", "ny rfp", "albany", "state authority"])
    is_jwiz = any(k in lower for k in ["jwiz", "jewish", "directory", "contractor", "plumber", "electrician", "local business"])
    is_nyscr = any(k in lower for k in ["nyscr", "contract reporter", "state contract", "agency contract", "state agency"])

    # ─────────────────────────────────────────────────────────────
    # 2. CROSS-QUESTIONING LOGIC BASED ON CONVERSATION STAGE
    # ─────────────────────────────────────────────────────────────
    if is_bonfire and not is_jwiz and not is_dasny and not is_nyscr:
        recommended_script = "bonfire"
        req_data["selectedScript"] = "bonfire"
        req_data["selectedScriptName"] = "Dallas City Hall Bonfire Scraper"
        req_data["location"] = "Dallas, Texas, USA"
        req_data["industry"] = "Municipal Procurement & Construction"

        # Check if user already provided specific category
        if any(c in lower for c in ["street sweeping", "sweeping", "paving", "repair", "stagehand", "labor", "flags", "it", "water"]):
            matched_cat = [c.title() for c in ["street sweeping", "paving", "stagehand", "flags"] if c in lower]
            cat_name = matched_cat[0] if matched_cat else "City Works"
            req_data["industry"] = f"City of Dallas: {cat_name}"
            req_data["completionPercentage"] = 65
            reply_text = (
                f"Understood! For **Dallas City Hall Bonfire Scraper**, targeting **{cat_name}**.\n\n"
                "Next question: How many open opportunity records do you want me to extract from the live portal?"
            )
            suggestions = ["10 records (Quick Scan)", "20 records (All Current)", "Full Portal Extract"]
        else:
            req_data["completionPercentage"] = 40
            reply_text = (
                "Great! You selected: 🏛️ **Dallas City Hall Bonfire Scraper**.\n\n"
                "**Cross-Question 1:** What specific project category or procurement type are you looking for in Dallas?"
            )
            suggestions = [
                "Street Sweeping Services",
                "Pavement & Road Repairs",
                "Temporary Stagehand & Labor",
                "All Open City Opportunities",
            ]

    elif is_dasny and not is_jwiz and not is_bonfire and not is_nyscr:
        recommended_script = "dasny"
        req_data["selectedScript"] = "dasny"
        req_data["selectedScriptName"] = "DASNY RFP & Bid Opportunities Scraper"
        req_data["location"] = "New York, USA"

        if any(c in lower for c in ["construction", "architectural", "engineering", "hvac", "renovation"]):
            matched_cat = "Construction & Engineering"
            req_data["industry"] = f"DASNY: {matched_cat}"
            req_data["completionPercentage"] = 65
            reply_text = (
                f"Target locked on **DASNY: {matched_cat}**.\n\n"
                "**Next question:** How many RFP opportunity records would you like me to collect?"
            )
            suggestions = ["10 RFPs", "20 RFPs (Default)", "50 RFPs"]
        else:
            req_data["completionPercentage"] = 40
            reply_text = (
                "Understood! Selected: 🏢 **DASNY RFP & Bid Opportunities Scraper** (Dormitory Authority of NY).\n\n"
                "**Cross-Question 1:** Which institutional sector or bid scope should we prioritize?"
            )
            suggestions = [
                "General Construction & Renovation",
                "Architectural & Engineering Services",
                "HVAC & Mechanical Systems",
                "All Active DASNY Bids",
            ]

    elif is_jwiz and not is_bonfire and not is_dasny and not is_nyscr:
        recommended_script = "jwiz"
        req_data["selectedScript"] = "jwiz"
        req_data["selectedScriptName"] = "JWiz Commercial Directory Scraper"

        # Check if trade and city provided
        has_trade = any(t in lower for t in ["contractor", "plumber", "electrician", "carpenter", "roofing", "hvac"])
        has_city = any(loc in lower for loc in ["new york", "brooklyn", "lakewood", "queens", "bronx", "jersey"])

        if has_trade and has_city:
            req_data["industry"] = f"Directory: {[t.title() for t in ['plumber', 'contractor', 'electrician'] if t in lower][0] if has_trade else 'Contractors'}"
            req_data["location"] = "New York Metro"
            req_data["completionPercentage"] = 70
            reply_text = (
                f"Target trade and city identified for **JWiz Commercial Directory Scraper**!\n\n"
                "**Next question:** What volume of verified business leads (company, direct phone, email) do you require?"
            )
            suggestions = ["10 Leads (Fast Test)", "25 Leads (Standard)", "50 Leads (Deep Extraction)"]
        elif has_trade:
            matched_trade = [t.title() for t in ["plumber", "contractor", "electrician", "hvac"] if t in lower][0]
            req_data["industry"] = f"Commercial {matched_trade} Services"
            req_data["completionPercentage"] = 50
            reply_text = (
                f"Selected trade: **{matched_trade}** on **JWiz Directory Scraper**.\n\n"
                "**Cross-Question 2:** Which city or metro area should I crawl?"
            )
            suggestions = [
                f"{matched_trade} in New York",
                f"{matched_trade} in Brooklyn",
                f"{matched_trade} in Lakewood",
            ]
        else:
            req_data["completionPercentage"] = 40
            reply_text = (
                "Selected: 📒 **JWiz Commercial & Services Directory Scraper**.\n\n"
                "**Cross-Question 1:** What business trade or service category do you want to harvest?"
            )
            suggestions = [
                "Commercial Contractors",
                "Plumbers & Pipefitters",
                "Electricians",
                "HVAC Specialists",
            ]

    elif is_nyscr and not is_bonfire and not is_dasny and not is_jwiz:
        recommended_script = "nyscr"
        req_data["selectedScript"] = "nyscr"
        req_data["selectedScriptName"] = "NYSCR State Contract Reporter Scraper"
        req_data["location"] = "New York, USA"

        if any(c in lower for c in ["services", "transportation", "commodities", "construction"]):
            req_data["industry"] = "NYS State Contracts"
            req_data["completionPercentage"] = 65
            reply_text = (
                "Criteria logged for **NYSCR State Contract Reporter Scraper**.\n\n"
                "**Next question:** How many open state contracts should I harvest for you?"
            )
            suggestions = ["10 Contracts", "25 Contracts (Recommended)", "All Open Bids"]
        else:
            req_data["completionPercentage"] = 40
            reply_text = (
                "Selected: 📜 **NYSCR State Contract Reporter Scraper**.\n\n"
                "**Cross-Question 1:** What type of state agency contracts or procurement categories are you seeking?"
            )
            suggestions = [
                "NYS Office of General Services",
                "Highway & Transportation Contracts",
                "Facility Maintenance & Security",
                "All Active NYSCR Ads",
            ]

    # Handle Record Quantity / Volume response
    elif any(char.isdigit() for char in lower) or any(k in lower for k in ["records", "leads", "bids", "rfps", "volume", "quantity"]):
        num = 20
        digits = "".join(filter(str.isdigit, text))
        if digits:
            num = int(digits)
        req_data["quantity"] = num
        req_data["completionPercentage"] = 100
        req_data["status"] = "ready_for_confirmation"

        script_name = req_data.get("selectedScriptName", "Autonomous Scraper Engine")
        reply_text = (
            f"Cross-questioning complete! Here is your finalized extraction brief:\n\n"
            f"• **Scraper Engine**: **{script_name}**\n"
            f"• **Target Scope**: {req_data.get('industry', 'All Open Opportunities')}\n"
            f"• **Target Location**: {req_data.get('location', 'Specified Region')}\n"
            f"• **Record Target**: **{num:,} verified records**\n\n"
            "The requirement is **100% complete**. Please review the summary panel on the right and click **Confirm & Generate Data** to launch live extraction!"
        )
        suggestions = ["Confirm & Generate Data", "Change Target Volume", "Select Different Scraper"]

    # If user provides a specific category answer based on current active script
    elif current_script:
        req_data["industry"] = text
        req_data["completionPercentage"] = max(req_data.get("completionPercentage", 0), 75)
        script_name = req_data.get("selectedScriptName", current_script.upper())
        reply_text = (
            f"Category set to: **\"{text}\"** for **{script_name}**.\n\n"
            "**Final Question:** How many verified records do you want to extract?"
        )
        suggestions = ["10 records", "20 records", "50 records"]

    # Initial Welcome & Scraper Engine Overview
    else:
        req_data["completionPercentage"] = 25
        reply_text = (
            f"Hello! I am your Autonomous Data Operations Agent. "
            "I will cross-question you to understand your exact requirements, then deploy the optimal scraper:\n\n"
            "1. 🏛️ **Dallas City Hall Bonfire Scraper** — (City procurement bids, RFPs, road repairs, street sweeping)\n"
            "2. 🏢 **DASNY Scraper** — (New York Dormitory Authority construction & architectural RFPs)\n"
            "3. 📒 **JWiz Directory Scraper** — (Commercial contractors, plumbers, electricians with verified phone/email)\n"
            "4. 📜 **NYSCR Scraper** — (Official New York State Contract Reporter public bids)\n\n"
            "**Question 1:** Which scraper engine or data source would you like to use?"
        )
        suggestions = [
            "Dallas City Hall Bonfire Scraper",
            "DASNY Scraper",
            "JWiz Directory Scraper",
            "NYSCR Scraper",
        ]

    return {
        "reply": reply_text,
        "suggestions": suggestions,
        "updatedRequirement": req_data,
        "recommendedScript": recommended_script,
    }


@app.post("/api/bot/confirm-and-generate")
def bot_confirm_and_generate(req: BotConfirmRequest):
    """
    Called when the user clicks 'Confirm & Generate Data' in the bot UI.
    Selects the optimal scraper engine, triggers the job in background, and returns the jobId.
    """
    req_data = req.requirement
    industry = (req_data.get("industry") or "").lower()
    location = (req_data.get("location") or "").lower()
    quantity = req_data.get("quantity") or 20

    # Determine scraper script
    script_id = req.preferredScriptId or req_data.get("selectedScript")
    if not script_id:
        if "dallas" in location or "texas" in location or "bonfire" in industry:
            script_id = "bonfire"
        elif "dasny" in industry or "dormitory" in industry:
            script_id = "dasny"
        elif "directory" in industry or "contractor" in industry or "jwiz" in industry:
            script_id = "jwiz"
        elif "nyscr" in industry or "state agency" in industry:
            script_id = "nyscr"
        else:
            script_id = "bonfire"

    # Derive dynamic keyword for JWiz from user prompt
    kw = "contractor"
    for candidate in ["plumber", "electrician", "contractor", "carpenter", "roofing", "hvac"]:
        if candidate in industry or candidate in location:
            kw = candidate
            break

    loc = "new-york"
    for loc_cand in ["brooklyn", "lakewood", "queens", "bronx", "new-york"]:
        if loc_cand in location or loc_cand in industry:
            loc = loc_cand
            break

    parameters = {
        "limit": min(quantity, 50),
        "location": loc,
        "keyword": kw,
    }

    job_id = scraper_manager.create_job(script_id, parameters)
    job = scraper_manager.get_job(job_id)

    return {
        "success": True,
        "jobId": job_id,
        "scriptId": script_id,
        "datasetId": job.get("datasetId") if job else f"ds-{job_id}",
        "message": f"Autonomous pipeline initiated using {script_id.upper()} engine.",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
