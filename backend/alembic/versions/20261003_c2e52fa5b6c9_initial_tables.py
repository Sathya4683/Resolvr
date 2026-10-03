"""initial tables

Revision ID: c2e52fa5b6c9
Revises: 
Create Date: 2026-10-03 13:37:16.085182

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from app.config import settings

#revision identifiers, used by alembic
revision: str = 'c2e52fa5b6c9'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    #vector size follows EMBEDDING_DIM, changing the model to a different size needs a new migration
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    #seeded history uses TCK-10001.. and KB-001..KB-035, new rows continue from these
    op.execute("CREATE SEQUENCE ticket_ref_seq START 20001")
    op.execute("CREATE SEQUENCE kb_ref_seq START 36")
    op.create_table('categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('slug', sa.String(length=60), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('product', sa.String(length=20), nullable=True),
    sa.Column('default_severity', sa.String(length=10), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('slug')
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=50), nullable=False),
    sa.Column('full_name', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=200), nullable=True),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('password_hash', sa.String(length=100), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_table('audit_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=50), nullable=False),
    sa.Column('entity_type', sa.String(length=30), nullable=True),
    sa.Column('entity_id', sa.String(length=40), nullable=True),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_created_at'), 'audit_logs', ['created_at'], unique=False)
    op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'], unique=False)
    op.create_table('batch_jobs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('filename', sa.String(length=200), nullable=True),
    sa.Column('total', sa.Integer(), nullable=False),
    sa.Column('processed', sa.Integer(), nullable=False),
    sa.Column('failed', sa.Integer(), nullable=False),
    sa.Column('rows', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('results', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_batch_jobs_status'), 'batch_jobs', ['status'], unique=False)
    op.create_table('digest_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('report_date', sa.Date(), nullable=False),
    sa.Column('trigger', sa.String(length=10), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('recipients', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('triggered_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['triggered_by_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('digest_runs_one_cron_per_day', 'digest_runs', ['report_date'], unique=True, postgresql_where=sa.text("trigger = 'cron'"))
    op.create_table('kb_articles',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ref', sa.String(length=20), server_default=sa.text("'KB-' || lpad(nextval('kb_ref_seq')::text, 3, '0')"), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('product', sa.String(length=20), nullable=True),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('tags', postgresql.ARRAY(sa.String()), nullable=False),
    sa.Column('content_md', sa.Text(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('updated_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['updated_by_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('ref')
    )
    op.create_table('notifications',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('body', sa.Text(), nullable=True),
    sa.Column('link', sa.String(length=200), nullable=True),
    sa.Column('is_read', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)
    op.create_table('tickets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ref', sa.String(length=20), server_default=sa.text("'TCK-' || nextval('ticket_ref_seq')"), nullable=False),
    sa.Column('customer_ref', sa.String(length=40), nullable=True),
    sa.Column('channel', sa.String(length=20), nullable=True),
    sa.Column('city', sa.String(length=60), nullable=True),
    sa.Column('subject', sa.String(length=200), nullable=True),
    sa.Column('complaint', sa.Text(), nullable=False),
    sa.Column('product_hint', sa.String(length=20), nullable=True),
    sa.Column('language', sa.String(length=10), nullable=False),
    sa.Column('product', sa.String(length=20), nullable=True),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('severity', sa.String(length=10), nullable=True),
    sa.Column('critical_reason', sa.String(length=20), nullable=True),
    sa.Column('sentiment', sa.String(length=12), nullable=True),
    sa.Column('ticket_type', sa.String(length=20), nullable=True),
    sa.Column('tags', postgresql.ARRAY(sa.String()), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('resolution_steps', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('resolution_summary', sa.Text(), nullable=True),
    sa.Column('is_searchable', sa.Boolean(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=True),
    sa.Column('embedding', Vector(settings.embedding_dim), nullable=True),
    sa.Column('embedding_model', sa.String(length=100), nullable=True),
    sa.Column('tsv', postgresql.TSVECTOR(), sa.Computed("to_tsvector('english', coalesce(subject, '') || ' ' || complaint || ' ' || coalesce(resolution_summary, ''))", persisted=True), nullable=True),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('resolved_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['resolved_by_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('content_hash'),
    sa.UniqueConstraint('ref')
    )
    op.create_index(op.f('ix_tickets_category_id'), 'tickets', ['category_id'], unique=False)
    op.create_index(op.f('ix_tickets_created_at'), 'tickets', ['created_at'], unique=False)
    op.create_index(op.f('ix_tickets_created_by_id'), 'tickets', ['created_by_id'], unique=False)
    op.create_index(op.f('ix_tickets_is_searchable'), 'tickets', ['is_searchable'], unique=False)
    op.create_index(op.f('ix_tickets_product'), 'tickets', ['product'], unique=False)
    op.create_index(op.f('ix_tickets_resolved_at'), 'tickets', ['resolved_at'], unique=False)
    op.create_index(op.f('ix_tickets_severity'), 'tickets', ['severity'], unique=False)
    op.create_index(op.f('ix_tickets_status'), 'tickets', ['status'], unique=False)
    op.create_index('tickets_embedding_idx', 'tickets', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('tickets_tsv_idx', 'tickets', ['tsv'], unique=False, postgresql_using='gin')
    op.create_table('analyses',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ticket_id', sa.Integer(), nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('parsed', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('retrieved', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('draft', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('outcome', sa.String(length=20), nullable=False),
    sa.Column('abstain_reason', sa.Text(), nullable=True),
    sa.Column('citation_check', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('confidence', sa.Double(), nullable=True),
    sa.Column('review_status', sa.String(length=20), nullable=False),
    sa.Column('final_steps', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('last_alerted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('latency_ms', sa.Integer(), nullable=True),
    sa.Column('timings', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('prompt_tokens', sa.Integer(), nullable=False),
    sa.Column('completion_tokens', sa.Integer(), nullable=False),
    sa.Column('cost_usd', sa.Numeric(precision=10, scale=6), nullable=False),
    sa.Column('model', sa.String(length=80), nullable=True),
    sa.Column('trace_id', sa.String(length=40), nullable=True),
    sa.Column('claimed_by_id', sa.Integer(), nullable=True),
    sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['claimed_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_analyses_created_at'), 'analyses', ['created_at'], unique=False)
    op.create_index(op.f('ix_analyses_review_status'), 'analyses', ['review_status'], unique=False)
    op.create_index(op.f('ix_analyses_ticket_id'), 'analyses', ['ticket_id'], unique=False)
    op.create_table('chat_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('ticket_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_sessions_user_id'), 'chat_sessions', ['user_id'], unique=False)
    op.create_table('kb_chunks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('article_id', sa.Integer(), nullable=False),
    sa.Column('chunk_index', sa.Integer(), nullable=False),
    sa.Column('heading', sa.String(length=200), nullable=True),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('embedding', Vector(settings.embedding_dim), nullable=True),
    sa.Column('embedding_model', sa.String(length=100), nullable=True),
    sa.Column('tsv', postgresql.TSVECTOR(), sa.Computed("to_tsvector('english', content)", persisted=True), nullable=True),
    sa.ForeignKeyConstraint(['article_id'], ['kb_articles.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_kb_chunks_article_id'), 'kb_chunks', ['article_id'], unique=False)
    op.create_index('kb_chunks_embedding_idx', 'kb_chunks', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index('kb_chunks_tsv_idx', 'kb_chunks', ['tsv'], unique=False, postgresql_using='gin')
    op.create_table('analyst_reviews',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('analysis_id', sa.Integer(), nullable=False),
    sa.Column('analyst_id', sa.Integer(), nullable=False),
    sa.Column('verdict', sa.String(length=20), nullable=False),
    sa.Column('citations_ok', sa.Boolean(), nullable=False),
    sa.Column('rubric', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('original_labels', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('corrected_labels', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('guidance_text', sa.Text(), nullable=True),
    sa.Column('embedding', Vector(settings.embedding_dim), nullable=True),
    sa.Column('embedding_model', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['analysis_id'], ['analyses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['analyst_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('analysis_id')
    )
    op.create_index('analyst_reviews_embedding_idx', 'analyst_reviews', ['embedding'], unique=False, postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.create_index(op.f('ix_analyst_reviews_analyst_id'), 'analyst_reviews', ['analyst_id'], unique=False)
    op.create_index(op.f('ix_analyst_reviews_created_at'), 'analyst_reviews', ['created_at'], unique=False)
    op.create_table('chat_messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('session_id', sa.Integer(), nullable=False),
    sa.Column('role', sa.String(length=10), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('sources', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('prompt_tokens', sa.Integer(), nullable=False),
    sa.Column('completion_tokens', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_chat_messages_session_id'), 'chat_messages', ['session_id'], unique=False)
    op.create_table('feedback',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('analysis_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('rating', sa.String(length=4), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['analysis_id'], ['analyses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('analysis_id', 'user_id', name='feedback_one_per_user')
    )
    op.create_index(op.f('ix_feedback_analysis_id'), 'feedback', ['analysis_id'], unique=False)
    op.create_table('review_decisions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('analysis_id', sa.Integer(), nullable=False),
    sa.Column('admin_id', sa.Integer(), nullable=False),
    sa.Column('action', sa.String(length=10), nullable=False),
    sa.Column('comment', sa.Text(), nullable=True),
    sa.Column('edited_steps', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['admin_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['analysis_id'], ['analyses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_review_decisions_analysis_id'), 'review_decisions', ['analysis_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_review_decisions_analysis_id'), table_name='review_decisions')
    op.drop_table('review_decisions')
    op.drop_index(op.f('ix_feedback_analysis_id'), table_name='feedback')
    op.drop_table('feedback')
    op.drop_index(op.f('ix_chat_messages_session_id'), table_name='chat_messages')
    op.drop_table('chat_messages')
    op.drop_index(op.f('ix_analyst_reviews_created_at'), table_name='analyst_reviews')
    op.drop_index(op.f('ix_analyst_reviews_analyst_id'), table_name='analyst_reviews')
    op.drop_index('analyst_reviews_embedding_idx', table_name='analyst_reviews', postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_table('analyst_reviews')
    op.drop_index('kb_chunks_tsv_idx', table_name='kb_chunks', postgresql_using='gin')
    op.drop_index('kb_chunks_embedding_idx', table_name='kb_chunks', postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_index(op.f('ix_kb_chunks_article_id'), table_name='kb_chunks')
    op.drop_table('kb_chunks')
    op.drop_index(op.f('ix_chat_sessions_user_id'), table_name='chat_sessions')
    op.drop_table('chat_sessions')
    op.drop_index(op.f('ix_analyses_ticket_id'), table_name='analyses')
    op.drop_index(op.f('ix_analyses_review_status'), table_name='analyses')
    op.drop_index(op.f('ix_analyses_created_at'), table_name='analyses')
    op.drop_table('analyses')
    op.drop_index('tickets_tsv_idx', table_name='tickets', postgresql_using='gin')
    op.drop_index('tickets_embedding_idx', table_name='tickets', postgresql_using='hnsw', postgresql_with={'m': 16, 'ef_construction': 64}, postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_index(op.f('ix_tickets_status'), table_name='tickets')
    op.drop_index(op.f('ix_tickets_severity'), table_name='tickets')
    op.drop_index(op.f('ix_tickets_resolved_at'), table_name='tickets')
    op.drop_index(op.f('ix_tickets_product'), table_name='tickets')
    op.drop_index(op.f('ix_tickets_is_searchable'), table_name='tickets')
    op.drop_index(op.f('ix_tickets_created_by_id'), table_name='tickets')
    op.drop_index(op.f('ix_tickets_created_at'), table_name='tickets')
    op.drop_index(op.f('ix_tickets_category_id'), table_name='tickets')
    op.drop_table('tickets')
    op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
    op.drop_table('notifications')
    op.drop_table('kb_articles')
    op.drop_index('digest_runs_one_cron_per_day', table_name='digest_runs', postgresql_where=sa.text("trigger = 'cron'"))
    op.drop_table('digest_runs')
    op.drop_index(op.f('ix_batch_jobs_status'), table_name='batch_jobs')
    op.drop_table('batch_jobs')
    op.drop_index(op.f('ix_audit_logs_user_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_created_at'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_action'), table_name='audit_logs')
    op.drop_table('audit_logs')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_role'), table_name='users')
    op.drop_table('users')
    op.drop_table('categories')
    op.execute("DROP SEQUENCE IF EXISTS ticket_ref_seq")
    op.execute("DROP SEQUENCE IF EXISTS kb_ref_seq")
