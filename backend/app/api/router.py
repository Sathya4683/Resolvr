from fastapi import APIRouter

from app.api.v1 import (
    admin,
    approvals,
    auth,
    batch,
    categories,
    chat,
    data,
    knowledge,
    notifications,
    reports,
    reviews,
    tickets,
    users,
    webhooks,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(tickets.router)
api_router.include_router(categories.router)
api_router.include_router(knowledge.router)
api_router.include_router(data.router)
api_router.include_router(approvals.router)
api_router.include_router(notifications.router)
api_router.include_router(batch.router)
api_router.include_router(chat.router)
api_router.include_router(admin.router)
api_router.include_router(reviews.router)
api_router.include_router(reports.router)
api_router.include_router(webhooks.router)
