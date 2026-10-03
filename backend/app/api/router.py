from fastapi import APIRouter

from app.api.v1 import auth, categories, data, knowledge, tickets, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(tickets.router)
api_router.include_router(categories.router)
api_router.include_router(knowledge.router)
api_router.include_router(data.router)
