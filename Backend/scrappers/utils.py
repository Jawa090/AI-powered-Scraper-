import re
from datetime import datetime, date
from typing import Any, Optional, Dict

from zoneinfo import ZoneInfo
from dateutil.parser import parse as parse_date, ParserError

# Reuse normalize_state from Database
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from Database.normalize import normalize_state

def clean(text: Any) -> Optional[str]:
    if text is None:
        return None
    if not isinstance(text, str):
        text = str(text)
    return " ".join(text.split())

def to_json_safe(obj: Any) -> Any:
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, (set, tuple)):
        return [to_json_safe(item) for item in obj]
    if isinstance(obj, dict):
        return {k: to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_json_safe(item) for item in obj]
    return obj

def state_code(value: Any) -> Optional[str]:
    return normalize_state(value)

def parse_local_dt(raw: str, tz_name: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = parse_date(raw, tzinfos={"CST": -21600, "CDT": -18000, "EST": -18000, "EDT": -14400})
        tz = ZoneInfo(tz_name)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tz)
        return dt.astimezone(tz)
    except (ParserError, ValueError, OverflowError, TypeError):
        return None

FILLER_WORDS = {"bid", "bids", "rfp", "rfps", "lead", "leads", "opportunity", "opportunities", "in", "for", "the", "and", "of"}

def keyword_match(text: str, keyword: str) -> bool:
    if not text or not keyword:
        return True
    
    words = [w for w in keyword.lower().split() if w not in FILLER_WORDS]
    if not words:
        return True
        
    text_lower = text.lower()
    return all(w in text_lower for w in words)

def location_match(rec_city: Optional[str], rec_state: Optional[str], params: Any) -> bool:
    param_state = state_code(getattr(params, 'us_state', None))
    param_city = getattr(params, 'city', None)
    
    if param_city or param_state:
        # Ignore params.location
        if param_state:
            rs = state_code(rec_state)
            if not rs or rs != param_state:
                return False
        if param_city:
            from Database.search import normalize_city
            if not rec_city or normalize_city(param_city).casefold() != normalize_city(rec_city).casefold():
                return False
        return True
    
    param_loc = getattr(params, 'location', None)
    if param_loc:
        if rec_city and param_loc.lower() in rec_city.lower():
            return True
        rs = state_code(rec_state)
        ps = state_code(param_loc)
        if rs and ps and rs == ps:
            return True
        return False
        
    return True
