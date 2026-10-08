from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Dict

from services.auth import get_current_user
from Database.models.user import User
from scrappers.controller import list_scrapers, to_api_dict, get_meta
from scrappers.base import UnknownScraper

router = APIRouter(prefix="/api/scripts", tags=["Scripts"])

@router.get("")
def list_scripts(current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Returns all registered scraping scripts with live metadata."""
    return {"scripts": [to_api_dict(meta) for meta in list_scrapers()]}

@router.get("/{script_id}")
def get_script_detail(script_id: str, current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    try:
        meta = get_meta(script_id)
        return {"script": to_api_dict(meta)}
    except UnknownScraper:
        raise HTTPException(status_code=404, detail=f"Script '{script_id}' not found.")

