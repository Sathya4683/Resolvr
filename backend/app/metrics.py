from prometheus_client import Counter, Gauge, Histogram

#http
HTTP_REQUESTS = Counter(
    "resolvr_http_requests_total", "HTTP requests handled", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "resolvr_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 15, 30, 60),
)

#llm
LLM_CALLS = Counter("resolvr_llm_requests_total", "LLM calls", ["provider", "purpose", "status"])
LLM_LATENCY = Histogram(
    "resolvr_llm_latency_seconds", "LLM call latency", ["purpose"], buckets=(0.5, 1, 2, 4, 8, 15, 30, 60)
)
LLM_TOKENS = Counter("resolvr_llm_tokens_total", "LLM tokens used", ["purpose", "kind"])
LLM_COST = Counter("resolvr_llm_cost_usd_total", "Estimated LLM cost in USD", ["purpose"])

#pipeline
STAGE_LATENCY = Histogram(
    "resolvr_pipeline_stage_seconds",
    "Time spent in each analysis stage",
    ["stage"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 15, 30),
)
ANALYSES = Counter("resolvr_analyses_total", "Complaints analysed", ["severity", "review_status"])
ABSTENTIONS = Counter("resolvr_abstentions_total", "Analyses where we refused to draft", ["reason"])
CITATION_FAILURES = Counter(
    "resolvr_citation_failures_total", "Drafts that cited sources we did not retrieve", ["outcome"]
)
OUTAGE_ALERTS = Counter("resolvr_outage_alerts_total", "Possible outages detected")

#workflow, these gauges are refreshed from the db whenever /metrics is scraped
PENDING_APPROVALS = Gauge("resolvr_pending_approvals", "Critical drafts waiting for an admin")
OLDEST_PENDING = Gauge("resolvr_oldest_pending_approval_seconds", "Age of the oldest pending approval")
ANALYST_AGREEMENT = Gauge(
    "resolvr_analyst_agreement_ratio", "Share of AI labels analysts agreed with", ["field"]
)
ANALYST_VERDICTS = Gauge("resolvr_analyst_verdicts", "Analyst verdicts so far", ["verdict"])
SEARCHABLE_DOCS = Gauge("resolvr_searchable_documents", "Documents in the retrieval pool", ["kind"])

FEEDBACK = Counter("resolvr_feedback_total", "Thumbs up/down from support agents", ["rating"])
INGESTED = Counter("resolvr_ingested_rows_total", "Rows ingested into the knowledge pool", ["kind", "status"])
JOBS = Counter("resolvr_batch_jobs_total", "Batch jobs by final status", ["kind", "status"])
NOTIFICATIONS = Counter("resolvr_notifications_total", "Notifications sent", ["channel", "status"])
DIGESTS = Counter("resolvr_digest_runs_total", "Daily digest runs", ["status"])
CHAT_MESSAGES = Counter("resolvr_chat_messages_total", "Assistant chat answers", ["status"])
CLIENT_ERRORS = Counter("resolvr_frontend_errors_total", "Errors reported by the browser")
