"""CORS configuration for the frontend.

Origins are read from CORS_ALLOWED_ORIGINS (comma-separated). Defaults to
common local Vite dev-server ports so `npm run dev` works against a
locally running API with no extra configuration.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

_DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def install_cors(app: FastAPI) -> None:
    origins_env = os.getenv("CORS_ALLOWED_ORIGINS", _DEFAULT_ORIGINS)
    origins = [o.strip() for o in origins_env.split(",") if o.strip()]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
