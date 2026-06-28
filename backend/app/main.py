from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import hmac
import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .database import init_db
from .routers.dashboard import router as dashboard_router
from .routers.data import router as data_router
from .routers.feishu import router as feishu_router
from .routers.intake import router as intake_router
from .routers.logs import router as logs_router
from .routers.mcp import router as mcp_router
from .routers.model_profiles import router as model_profiles_router
from .routers.modules import router as modules_router
from .routers.product import router as product_router
from .routers.queue import router as queue_router
from .routers.workflows import router as workflows_router
from .routers.xhs import router as xhs_router
from tools.feishu_intake.listener import start_intake_worker


def cors_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000")
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    return origins or ["http://127.0.0.1:3000", "http://localhost:3000"]


def admin_token() -> str:
    return os.getenv("ADMIN_TOKEN", "").strip()


def request_admin_token(request: Request) -> str:
    header_token = request.headers.get("x-admin-token", "").strip()
    if header_token:
        return header_token
    authorization = request.headers.get("authorization", "").strip()
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return ""


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    start_intake_worker()
    yield


app = FastAPI(title="AI 自动化控制台 Lite", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def admin_token_middleware(request: Request, call_next: Any) -> Any:
    expected = admin_token()
    if expected and request.url.path.startswith("/api/") and request.url.path != "/api/health":
        provided = request_admin_token(request)
        if not provided or not hmac.compare_digest(provided, expected):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


app.include_router(dashboard_router)
app.include_router(modules_router)
app.include_router(model_profiles_router)
app.include_router(feishu_router)
app.include_router(mcp_router)
app.include_router(product_router)
app.include_router(intake_router)
app.include_router(workflows_router)
app.include_router(logs_router)
app.include_router(queue_router)
app.include_router(data_router)
app.include_router(xhs_router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
