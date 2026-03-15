"""
ConductorAI UI — SQLite Database (aiosqlite)
"""

from __future__ import annotations

import aiosqlite
from pathlib import Path

_db: aiosqlite.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id                          TEXT PRIMARY KEY,
    name                        TEXT NOT NULL,
    github_repo                 TEXT NOT NULL,
    github_app_installation_id  INTEGER,
    requirements_yaml           TEXT,
    infra_yaml                  TEXT,
    last_pipeline_yaml          TEXT,
    selected_components         TEXT DEFAULT '[]',
    created_at                  TEXT DEFAULT (datetime('now')),
    updated_at                  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id                  TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL REFERENCES projects(id),
    status              TEXT NOT NULL DEFAULT 'pending',
    selected_components TEXT DEFAULT '[]',
    workflow_id         TEXT,
    pipeline_yaml       TEXT,
    result_summary      TEXT,
    error_log           TEXT,
    created_at          TEXT DEFAULT (datetime('now')),
    completed_at        TEXT
);

CREATE TABLE IF NOT EXISTS pr_reviews (
    id                TEXT PRIMARY KEY,
    project_id        TEXT NOT NULL REFERENCES projects(id),
    pr_number         INTEGER NOT NULL,
    pr_title          TEXT,
    complexity_score  REAL,
    quality_score     REAL,
    review_summary    TEXT,
    review_comments   TEXT,
    findings          TEXT,
    recommendations   TEXT,
    reviewed_at       TEXT DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_github_repo
    ON projects(github_repo);
"""


async def init_db(db_path: str) -> None:
    global _db
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    _db = await aiosqlite.connect(db_path)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(SCHEMA)
    await _db.commit()


async def get_db() -> aiosqlite.Connection:
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db


async def close_db() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None
