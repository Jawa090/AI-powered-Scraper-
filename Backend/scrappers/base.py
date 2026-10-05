from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field

class ScrapeParams(BaseModel):
    limit: int = 20
    location: Optional[str] = None
    keyword: Optional[str] = None
    timeout_s: int = 60

class RawRecord(BaseModel):
    external_id: str
    source_url: str
    
    # Optional standard fields
    organization_name: Optional[str] = None
    contact_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    location: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    notes: Optional[str] = None
    
    # Any other dynamic fields
    lead_metadata: Dict[str, Any] = Field(default_factory=dict)

class BaseScraper(ABC):
    source_code: str

    @abstractmethod
    def run(self, params: ScrapeParams) -> Iterator[RawRecord]:
        """Execute the scrape returning an iterator of RawRecords."""
        pass
        
    def check_credentials(self) -> tuple[bool, Optional[str]]:
        """Pre-flight check for required credentials. Defaults to True if none required."""
        return True, None
