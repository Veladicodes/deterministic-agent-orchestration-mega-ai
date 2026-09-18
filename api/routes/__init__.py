from fastapi import APIRouter

from api.routes.health import router as health_router
from api.routes.stream import router as stream_router
from api.routes.query import router as query_router
from api.routes.replay import router as replay_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(stream_router)
api_router.include_router(query_router)
api_router.include_router(replay_router)
