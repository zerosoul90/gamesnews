from pydantic import BaseModel, HttpUrl
from typing import Literal

SourceStatus = Literal["active", "inactive", "error"]

class Source(BaseModel):
    name: str
    url: str # feed URL
    language: str = "en" # "en" or "vi"
    reliability_score: int = 100 # Ngưỡng tin cậy, 0-100
    status: SourceStatus = "active"
    last_crawled_at: str | None = None # ISO format
    
    def to_mongo(self) -> dict:
        return self.model_dump(mode="json")
