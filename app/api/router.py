from fastapi import APIRouter

from app.api.routes import customers, health, knowledge, proposals, rfps

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(customers.router)
api_router.include_router(knowledge.router)
api_router.include_router(proposals.router)
api_router.include_router(rfps.router)
