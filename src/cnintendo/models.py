from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class IssueMetadata(BaseModel):
    id: Optional[str] = None
    filename: str
    number: Optional[int] = None
    year: Optional[int] = None
    month: Optional[str] = None
    pages: int = Field(..., ge=1)
    type: Literal["native", "scanned", "mixed", "unknown"] = "unknown"
    ia_title: Optional[str] = None
    ia_subjects: list[str] = Field(default_factory=list)
    ia_date: Optional[str] = None
    ia_identifier: Optional[str] = None


class ImageInfo(BaseModel):
    path: str = Field(..., min_length=1)
    description: Optional[str] = None


class Article(BaseModel):
    page: int = Field(..., ge=1)
    section: str = "unknown"
    title: Optional[str] = None
    game: Optional[str] = None
    platform: Optional[str] = None
    score: Optional[float] = None
    text: Optional[str] = None
    images: list[ImageInfo] = Field(default_factory=list)

    @field_validator("images", mode="before")
    @classmethod
    def coerce_images(cls, v: list) -> list:
        result = []
        for item in v:
            if isinstance(item, str):
                result.append({"path": item, "description": None})
            else:
                result.append(item)
        return result


class IssueData(BaseModel):
    issue: IssueMetadata
    articles: list[Article] = Field(default_factory=list)
    summary: Optional[str] = None
    pages_clean: list[dict] = Field(default_factory=list)


class PageProcessed(BaseModel):
    page_number: int = Field(..., ge=1)
    page_type_scandata: Optional[str] = None  # "Title", "Normal", etc from scandata.xml
    image_path: Optional[str] = None
    djvu_text: Optional[str] = None
    llm: Optional[dict] = None  # Opaque — raw OpenAI response, no internal validation


class IssuePages(BaseModel):
    ia_identifier: str
    ia_title: Optional[str] = None
    ia_date: Optional[str] = None
    ia_description: Optional[str] = None     # <description> stripped of HTML
    ia_clubnintendo: Optional[str] = None    # <clubnintendo> e.g. "No1408"
    ia_subjects: list[str] = Field(default_factory=list)
    canonical_stem: str
    filename: str
    total_pages: int = Field(..., ge=0)
    pages: list[PageProcessed] = Field(default_factory=list)
