from typing import Any, Literal

from pydantic import BaseModel

SourceStatus = Literal["active", "inactive", "error"]

class Source(BaseModel):
    name: str
    url: str # feed URL
    language: str = "en" # "en" or "vi"
    reliability_score: int = 100 # Ngưỡng tin cậy, 0-100
    status: SourceStatus = "active"
    last_crawled_at: str | None = None # ISO format

    def to_mongo(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
