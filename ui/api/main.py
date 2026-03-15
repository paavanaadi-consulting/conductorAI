"""
ConductorAI UI — FastAPI Application
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ui.api.config import get_settings
from ui.api.database import init_db, close_db
from ui.api.services.conductor_service import ConductorService
from ui.api.services.github_service import GitHubService
from ui.api.routers import projects, workflows, templates, github, upload, ws


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Database
    await init_db(settings.database_path)

    # ConductorAI service
    conductor_svc = ConductorService(settings)
    await conductor_svc.initialize()
    app.state.conductor = conductor_svc

    # GitHub service
    app.state.github = GitHubService(settings)

    yield

    await conductor_svc.shutdown()
    await close_db()


app = FastAPI(
    title="ConductorAI",
    version="0.1.0",
    description="Web UI API for ConductorAI orchestration framework",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(workflows.router, prefix="/api/workflows", tags=["workflows"])
app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
app.include_router(github.router, prefix="/api/github", tags=["github"])
app.include_router(upload.router, prefix="/api/upload", tags=["upload"])
app.include_router(ws.router, prefix="/api/ws", tags=["websocket"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}
