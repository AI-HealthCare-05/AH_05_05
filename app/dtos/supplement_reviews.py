from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class SupplementReviewResponse(BaseModel):
    id: int
    author_label: str
    score: int | None
    review_body: str | None
    updated_at: datetime
    is_mine: bool
    reported_by_me: bool


class SupplementReviewListResponse(BaseModel):
    items: list[SupplementReviewResponse]
    total: int
    offset: int
    limit: int
    rating_average: Decimal | None
    review_count: int
