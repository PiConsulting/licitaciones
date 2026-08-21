from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


TrackingStatus = Literal["active", "completed"]
TrackingCategoryStatus = Literal["not_reviewed", "in_review", "closed"]
TrackingItemStatus = Literal["not_evaluated", "compliant", "non_compliant", "not_applicable"]
CommentScope = Literal["category", "checklist_item"]


class TrackingSourceItemRef(BaseModel):
    version_id: str
    field_name: str
    document_id: str | None = None
    page: int | None = None
    citation_hash: str | None = None


class TrackingItem(BaseModel):
    tracking_item_id: str
    category_key: str
    source_item_ref: TrackingSourceItemRef
    status: TrackingItemStatus = "not_evaluated"
    updated_by: str | None = None
    updated_at: datetime | None = None


class TrackingCategory(BaseModel):
    category_key: str
    status: TrackingCategoryStatus = "not_reviewed"
    updated_by: str | None = None
    updated_at: datetime | None = None
    closed_by: str | None = None
    closed_at: datetime | None = None
    reopened_by: str | None = None
    reopened_at: datetime | None = None
    items: list[TrackingItem] = Field(default_factory=list)
    comments_count: int = 0


class TrackingSummary(BaseModel):
    total_categories: int
    not_reviewed: int
    in_review: int
    closed: int
    closed_percentage: int


class AnalysisTracking(BaseModel):
    id: str
    type: Literal["tracking"] = "tracking"
    analysis_id: str
    version_id: str
    status: TrackingStatus = "active"
    started_by: str
    started_at: datetime
    completed_by: str | None = None
    completed_by_name: str | None = None
    completed_at: datetime | None = None
    updated_at: datetime
    categories: list[TrackingCategory]
    summary: TrackingSummary


class StartTrackingResponse(BaseModel):
    tracking: AnalysisTracking


class UpdateCategoryStatusRequest(BaseModel):
    status: TrackingCategoryStatus


class UpdateTrackingItemRequest(BaseModel):
    status: TrackingItemStatus


class CreateTrackingCommentRequest(BaseModel):
    scope: CommentScope
    content: str = Field(min_length=1, max_length=2000)
    tracking_item_id: str | None = None


class UpdateTrackingCommentRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class TrackingComment(BaseModel):
    id: str
    analysis_id: str
    version_id: str
    category_key: str
    scope: CommentScope
    tracking_item_id: str | None = None
    content: str
    created_by: str
    created_by_name: str | None = None
    created_at: datetime
    edited_by: str | None = None
    edited_by_name: str | None = None
    edited_at: datetime | None = None
    deleted: bool = False
    deleted_at: datetime | None = None
    deleted_by: str | None = None
