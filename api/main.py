from fastapi import FastAPI
from sqlalchemy import text

import redis.asyncio as aioredis

from api.routes import api_router
from api.middleware.cors import install_cors
from api.middleware.rate_limit import DailyRateLimitMiddleware
from shared.settings import get_settings
from shared.logging import configure_logging, get_logger
from db.session import engine

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)

install_cors(app)
app.add_middleware(DailyRateLimitMiddleware)


@app.on_event("startup")
async def startup_event() -> None:
    # Configure structured logging early so startup messages are captured
    configure_logging(settings.app_name, settings.log_level)
    logger = get_logger("api")

    logger.info("starting application")

    # Validate configuration
    try:
        settings.validate()
        logger.info("configuration validated")
    except Exception as exc:
        logger.exception("configuration validation failed: %s", exc)
        raise

    # Check DB connectivity
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("database connection OK")
    except Exception:
        logger.exception("database connection failed")

    # Check Redis connectivity
    try:
        r = aioredis.from_url(settings.redis_url)
        await r.ping()
        logger.info("redis connection OK")
    except Exception:
        logger.exception("redis connection failed")


app.include_router(api_router, prefix="/api/v1")
