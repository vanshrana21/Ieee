from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class SearchFilters(BaseModel):
    court: Optional[str] = None
    jurisdiction: Optional[str] = None
    year: Optional[str] = None


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    filters: Optional[SearchFilters] = None


class CaseTag(BaseModel):
    name: str


class SearchResult(BaseModel):
    id: str
    title: str
    court: str
    year: int
    summary: str
    citations: int
    tags: List[str] = []
    relevance_score: Optional[float] = None
    source: Optional[str] = "Mock Dataset (Demo)"


class SearchResponse(BaseModel):
    total_results: int
    results: List[SearchResult]
    query: str
    credits_used: int = 1


class CaseDetail(BaseModel):
    id: str
    title: str
    court: str
    year: int
    date: Optional[str] = None
    docket_number: Optional[str] = None
    summary: str
    holdings: Optional[str] = None
    key_points: Optional[List[str]] = None
    tags: List[str] = []
    citations: int
    cited_by: Optional[List[dict]] = None
    cites: Optional[List[dict]] = None
    statutes: Optional[List[dict]] = None
    source: Optional[str] = "Mock Dataset (Demo)"


class AISummaryRequest(BaseModel):
    case_id: str


class AISummaryResponse(BaseModel):
    case_id: str
    summary: str
    key_points: List[str]
    credits_used: int = 5