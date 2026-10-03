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


#---------------- taxonomy ----------------

Severity = Literal["low", "medium", "high", "critical"]


class CategoryOut(ORM):
    id: int
    slug: str
    name: str
    description: str
    product: str | None
    default_severity: str
    is_active: bool
    ticket_count: int = 0


class CategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str | None = Field(default=None, max_length=60, pattern=r"^[a-z0-9_]+$")
    description: str = Field(min_length=10, max_length=1000)
    product: Product | None = None
    default_severity: Severity = "medium"


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, min_length=10, max_length=1000)
    product: Product | None = None
    default_severity: Severity | None = None
    is_active: bool | None = None


class RelabelCandidate(BaseModel):
    ref: str
    subject: str | None
    snippet: str
    current_category: str | None
    similarity: float


class RelabelIn(BaseModel):
    refs: list[str] = Field(min_length=1, max_length=200)


#---------------- knowledge base ----------------

class KbArticleIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    content_md: str = Field(min_length=20, max_length=50_000)
    product: Product | None = None
    category_slug: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)


class KbArticleListItem(BaseModel):
    ref: str
    title: str
    product: str | None
    category: CategoryBrief | None
    tags: list[str]
    status: str
    version: int
    updated_at: datetime
    author: str | None
    excerpt: str


class KbArticleOut(KbArticleListItem):
    content_md: str
    chunks: int


#---------------- data import ----------------

class ImportReport(BaseModel):
    inserted: int = 0
    updated: int = 0
    duplicates: int = 0
    errors: list[dict] = Field(default_factory=list)


class ResolvedTicketIn(BaseModel):
    complaint: str = Field(min_length=5, max_length=4000)
    subject: str | None = Field(default=None, max_length=200)
    category: str
    product: Product | None = None
    severity: Severity
    sentiment: Literal["angry", "frustrated", "neutral", "positive"] | None = None
    resolution_steps: list[str] = Field(min_length=1, max_length=20)
    resolution_summary: str | None = Field(default=None, max_length=1000)


class PromoteIn(BaseModel):
    refs: list[str] = Field(min_length=1, max_length=200)


class PromotableTicket(BaseModel):
    ref: str
    subject: str | None
    snippet: str
    category: str | None
    severity: str | None
    resolved_at: datetime | None
    resolved_by: str | None
    steps: list[str]
    feedback: str | None
    analyst_verdict: str | None


#---------------- approvals / notifications ----------------

class StepIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    citations: list[str] = Field(default_factory=list, max_length=10)


class DecisionIn(BaseModel):
    action: Literal["approve", "edit", "reject"]
    comment: str | None = Field(default=None, max_length=1000)
    steps: list[StepIn] | None = Field(default=None, max_length=20)


class ApprovalItem(BaseModel):
    analysis_id: int
    ticket_ref: str
    subject: str | None
    snippet: str
    severity: str | None
    critical_reason: str | None
    category: str | None
    raised_by: str | None
    created_at: datetime
    waiting_minutes: int
    review_status: str
    decided_by: str | None = None
    decided_at: datetime | None = None
    comment: str | None = None


class NotificationOut(ORM):
    id: int
    kind: str
    title: str
    body: str | None
    link: str | None
    is_read: bool
    created_at: datetime


class ClientLogIn(BaseModel):
    level: Literal["error", "warning", "info"] = "error"
    message: str = Field(max_length=500)
    path: str | None = Field(default=None, max_length=200)
    source: str | None = Field(default=None, max_length=300)
    line: int | None = None


#---------------- batch jobs ----------------

class BatchJobOut(ORM):
    id: int
    kind: str
    status: str
    filename: str | None
    total: int
    processed: int
    failed: int
    results: list
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


#---------------- assistant chat ----------------

class ChatSessionIn(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    ticket_ref: str | None = Field(default=None, max_length=20)


class ChatSessionOut(BaseModel):
    id: int
    title: str
    ticket_ref: str | None
    created_at: datetime
    updated_at: datetime


class ChatMessageOut(ORM):
    id: int
    role: str
    content: str
    sources: list
    created_at: datetime


class ChatMessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)
