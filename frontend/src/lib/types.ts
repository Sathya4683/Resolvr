export type Role = 'support_agent' | 'admin' | 'analyst'
export type Severity = 'low' | 'medium' | 'high' | 'critical'
export type ReviewStatus = 'auto_approved' | 'pending_review' | 'approved' | 'edited' | 'rejected'

export interface User {
  id: number
  username: string
  full_name: string
  email: string | null
  role: Role
  is_active: boolean
  created_at: string
  last_login_at: string | null
}

export interface CategoryBrief {
  id: number
  slug: string
  name: string
}

export interface Category extends CategoryBrief {
  description: string
  product: string | null
  default_severity: Severity
  is_active: boolean
  ticket_count: number
}

export interface TicketListItem {
  id: number
  ref: string
  subject: string | null
  snippet: string
  status: string
  severity: Severity | null
  sentiment: string | null
  product: string | null
  category: CategoryBrief | null
  review_status: ReviewStatus | null
  source: string
  created_at: string
  created_by: string | null
}

export interface Source {
  ref: string
  kind: 'ticket' | 'kb'
  title: string
  snippet: string
  content: string
  category: string | null
  product: string | null
  similarity: number
  vector_rank: number | null
  keyword_rank: number | null
  rrf: number
  rerank_score: number | null
  matched_terms: string[]
  why: string
}

export interface Step {
  text: string
  citations: string[]
}

export interface Analysis {
  id: number
  parsed: {
    category: string | null
    product: string | null
    severity: Severity
    critical_reason: string | null
    sentiment: string
    language: string
    in_scope: boolean
    summary: string
    confidence: number
    llm_severity?: string
    rules_fired?: string[]
    pii_redacted?: string[]
    guidance_used?: string[]
    best_similarity?: number
  }
  retrieved: Source[]
  draft: { steps?: Step[]; customer_reply?: string; abstain?: boolean; abstain_reason?: string }
  draft_hidden: boolean
  steps: Step[]
  outcome: 'drafted' | 'abstained' | 'draft_unavailable'
  abstain_reason: string | null
  citation_check: { valid?: boolean; retried?: boolean; stripped?: boolean; problems?: string[] }
  review_status: ReviewStatus
  decision: { action: string; comment: string | null; admin: string; created_at: string } | null
  my_feedback: 'up' | 'down' | null
  latency_ms: number | null
  timings: Record<string, number>
  prompt_tokens: number
  completion_tokens: number
  cost_usd: number
  model: string | null
  trace_id: string | null
  created_at: string
}

export interface TicketDetail {
  id: number
  ref: string
  subject: string | null
  complaint: string
  customer_ref: string | null
  channel: string | null
  city: string | null
  product_hint: string | null
  status: string
  source: string
  severity: Severity | null
  critical_reason: string | null
  sentiment: string | null
  product: string | null
  language: string
  category: CategoryBrief | null
  tags: string[]
  resolution_steps: string[]
  resolution_summary: string | null
  is_searchable: boolean
  created_by: { id: number; username: string; full_name: string } | null
  created_at: string
  resolved_at: string | null
  analysis: Analysis | null
  can_edit: boolean
}

export interface KbArticle {
  ref: string
  title: string
  product: string | null
  category: CategoryBrief | null
  tags: string[]
  status: string
  version: number
  updated_at: string
  author: string | null
  excerpt: string
  content_md?: string
  chunks?: number
}

export interface ApprovalItem {
  analysis_id: number
  ticket_ref: string
  subject: string | null
  snippet: string
  severity: Severity | null
  critical_reason: string | null
  category: string | null
  raised_by: string | null
  created_at: string
  waiting_minutes: number
  review_status: ReviewStatus
  decided_by: string | null
  decided_at: string | null
  comment: string | null
}

export interface BatchResult {
  row: number
  ticket_ref?: string
  category?: string | null
  product?: string | null
  severity?: Severity | null
  sentiment?: string | null
  review_status?: ReviewStatus
  outcome?: string
  top_source?: string | null
  steps?: string[]
  error?: string
}

export interface BatchJob {
  id: number
  kind: string
  status: 'queued' | 'running' | 'done' | 'failed'
  filename: string | null
  total: number
  processed: number
  failed: number
  results: BatchResult[]
  error: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}
