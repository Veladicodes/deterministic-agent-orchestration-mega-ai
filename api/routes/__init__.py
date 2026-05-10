from fastapi import APIRouter

from api.routes.health import router as health_router
from api.routes.stream import router as stream_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(stream_router)
