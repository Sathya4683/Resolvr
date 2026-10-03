"""request / response models shared by the routers"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["support_agent", "admin", "analyst"]
EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


#---------------- auth / users ----------------

class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)
    #the login page has a tab per role, we check the account really has that role
    role: Role | None = None


class UserOut(ORM):
    id: int
    username: str
    full_name: str
    email: str | None
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-z0-9_.]+$")
    full_name: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=200, pattern=EMAIL_PATTERN)
    role: Role
    password: str = Field(min_length=8, max_length=200)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=200, pattern=EMAIL_PATTERN)
    role: Role | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)


#---------------- tickets / analyses ----------------

Channel = Literal["phone", "email", "chat", "app", "store", "webhook"]
Product = Literal["broadband", "mobile", "dth", "billing"]


class TicketCreate(BaseModel):
    complaint: str = Field(min_length=5, max_length=4000)
    subject: str | None = Field(default=None, max_length=200)
    customer_ref: str | None = Field(default=None, max_length=40)
    channel: Channel | None = None
    product_hint: Product | None = None


class CategoryBrief(ORM):
    id: int
    slug: str
    name: str


class UserBrief(ORM):
    id: int
    username: str
    full_name: str


class TicketListItem(BaseModel):
    id: int
    ref: str
    subject: str | None
    snippet: str
    status: str
    severity: str | None
    sentiment: str | None
    product: str | None
    category: CategoryBrief | None
    review_status: str | None
    source: str
    created_at: datetime
    created_by: str | None


class ReviewDecisionOut(BaseModel):
    action: str
    comment: str | None
    admin: str
    created_at: datetime


class AnalysisOut(BaseModel):
    id: int
    parsed: dict
    retrieved: list
    draft: dict
    #true when the agent isn't allowed to see the draft yet (pending admin review / rejected)
    draft_hidden: bool
    #the steps the agent should follow: admin edited ones if any, otherwise the draft
    steps: list[dict]
    outcome: str
    abstain_reason: str | None
    citation_check: dict
    review_status: str
    decision: ReviewDecisionOut | None
    my_feedback: str | None
    latency_ms: int | None
    timings: dict
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    model: str | None
    trace_id: str | None
    created_at: datetime


class TicketDetail(BaseModel):
    id: int
    ref: str
    subject: str | None
    complaint: str
    customer_ref: str | None
    channel: str | None
    city: str | None
    product_hint: str | None
    status: str
    source: str
    severity: str | None
    critical_reason: str | None
    sentiment: str | None
    product: str | None
    language: str
    category: CategoryBrief | None
    tags: list[str]
    resolution_steps: list[str]
    resolution_summary: str | None
    is_searchable: bool
    created_by: UserBrief | None
    created_at: datetime
    resolved_at: datetime | None
    analysis: AnalysisOut | None
    can_edit: bool


class ResolveIn(BaseModel):
    steps: list[str] | None = Field(default=None, max_length=20)
    summary: str | None = Field(default=None, max_length=1000)


class FeedbackIn(BaseModel):
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=1000)
