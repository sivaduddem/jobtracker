"""FastAPI dashboard — companies, jobs, polling status, search/filter."""

from __future__ import annotations

import csv
import io
import json
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

if TYPE_CHECKING:
    from core.scheduler import Scheduler
    from database.sqlite import Storage

ROOT = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(ROOT / "templates"))


def create_app(storage: Storage, scheduler: Scheduler | None = None) -> FastAPI:
    app = FastAPI(title="Internship Intelligence", version="0.1.0")
    app.state.storage = storage
    app.state.scheduler = scheduler

    static_dir = ROOT / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        stats = await storage.stats()
        jobs = await storage.list_internships(limit=50, sort="first_seen")
        companies = await storage.list_company_states()
        errors = await storage.recent_poll_errors(limit=20)
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "stats": stats,
                "jobs": jobs,
                "companies": companies,
                "errors": errors,
                "scheduler": scheduler,
            },
        )

    @app.get("/api/stats")
    async def api_stats() -> dict[str, Any]:
        stats = await storage.stats()
        if scheduler:
            stats["cycle_count"] = scheduler.cycle_count
            stats["last_cycle_at"] = (
                scheduler.last_cycle_at.isoformat() if scheduler.last_cycle_at else None
            )
            stats["companies_configured"] = len(scheduler.companies)
        return stats

    @app.get("/api/jobs")
    async def api_jobs(
        q: str | None = None,
        company: str | None = None,
        min_score: float | None = None,
        active: bool = True,
        sort: str = "first_seen",
        desc: bool = True,
        limit: int = Query(100, le=1000),
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        jobs = await storage.list_internships(
            active_only=active,
            company=company,
            search=q,
            min_score=min_score,
            limit=limit,
            offset=offset,
            sort=sort,
            descending=desc,
        )
        return [j.model_dump(mode="json") for j in jobs]

    @app.get("/api/companies")
    async def api_companies() -> list[dict[str, Any]]:
        states = await storage.list_company_states()
        return [s.model_dump(mode="json") for s in states]

    @app.get("/api/errors")
    async def api_errors(limit: int = 50) -> list[dict[str, Any]]:
        return await storage.recent_poll_errors(limit=limit)

    @app.post("/api/poll")
    async def api_poll(slug: str | None = None) -> dict[str, Any]:
        if not scheduler:
            return {"ok": False, "error": "scheduler not attached"}
        results = await scheduler.poll_now(slug)
        return {
            "ok": True,
            "polled": len(results),
            "new": sum(r.new_jobs for r in results),
            "errors": [r.error for r in results if r.error],
        }

    @app.get("/api/export/json")
    async def export_json() -> JSONResponse:
        data = await storage.export_json()
        return JSONResponse(data)

    @app.get("/api/export/csv")
    async def export_csv() -> StreamingResponse:
        rows = await storage.export_csv_rows()
        buf = io.StringIO()
        if rows:
            writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=internships.csv"},
        )

    @app.get("/api/history/{company}")
    async def company_history(company: str) -> list[dict[str, Any]]:
        hist = await storage.historical_for_company(company)
        return [h.model_dump(mode="json") for h in hist]

    @app.post("/api/applications/{dedupe_key}")
    async def upsert_application(
        dedupe_key: str,
        status: str = "saved",
        resume_version: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        from core.models import ApplicationRecord, ApplicationStatus
        from datetime import datetime

        try:
            app_status = ApplicationStatus(status)
        except ValueError:
            return {"ok": False, "error": f"invalid status: {status}"}
        record = ApplicationRecord(
            dedupe_key=dedupe_key,
            status=app_status,
            resume_version=resume_version,
            notes=notes,
            updated_at=datetime.utcnow(),
        )
        await storage.upsert_application(record)
        return {"ok": True, "application": record.model_dump(mode="json")}

    @app.get("/api/applications/{dedupe_key}")
    async def get_application(dedupe_key: str) -> dict[str, Any]:
        record = await storage.get_application(dedupe_key)
        if not record:
            return {"ok": False, "error": "not found"}
        return {"ok": True, "application": record.model_dump(mode="json")}

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
