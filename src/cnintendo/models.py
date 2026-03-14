from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


class IssueMetadata(BaseModel):
    id: Optional[str] = None
    filename: str
    number: Optional[int] = None
    year: Optional[int] = None
    month: Optional[str] = None
    pages: int = Field(..., ge=1)
    type: Literal["native", "scanned", "mixed", "unknown"] = "unknown"


class Article(BaseModel):
    page: int = Field(..., ge=1)
    section: str = "unknown"
    title: Optional[str] = None
    game: Optional[str] = None
    platform: Optional[str] = None
    score: Optional[float] = None
    text: Optional[str] = None
    images: list[str] = Field(default_factory=list)


class IssueData(BaseModel):
    issue: IssueMetadata
    articles: list[Article] = Field(default_factory=list)
