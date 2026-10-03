"""Dhaga Workbench API. Run: uvicorn backend.main:app --reload  (docs at /docs)

Modules never import each other; they only use backend.shared. That keeps the later split into
separate services a matter of moving folders.
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.modules.cx import service as cx_service
from backend.modules.cx.router import router as cx_router
from backend.modules.returns.router import router as returns_router
from backend.shared.errors import AppError, NotFound, install_error_handlers
from backend.shared.settings import ROOT, get_settings

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Dhaga Workbench API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
install_error_handlers(app)

app.include_router(returns_router, prefix="/api/returns")
app.include_router(cx_router, prefix="/api/cx")


@app.get("/api/health", tags=["health"])
def health():
    s = get_settings()
    try:
        deps = cx_service.get_deps()
        db_ok, policies = deps.repo.ping(), sorted(deps.kb.policies())
        issues = deps.repo.setup_issues() if db_ok else []
    except AppError as e:
        db_ok, policies, issues = False, [], [e.message]
    return {
        "status": "ok" if db_ok and not issues else "degraded",
        "setup_issues": issues,
        "cx_data_source": s.cx_mode,
        "returns_data_source": s.returns_mode,
        "database_reachable": db_ok,
        "llm_configured": s.llm_configured,
        "llm_provider": s.llm_provider,
        "models": {"fast": s.model_fast, "strong": s.model_strong},
        "policies_loaded": policies,
    }


# ---- Frontend: serve the built React app (frontend/dist) when it exists ----
FRONTEND_DIST = ROOT / "frontend" / "dist"

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str):
        if path.startswith("api/"):
            raise NotFound("NOT_FOUND", f"No API route /{path}")
        file = (FRONTEND_DIST / path).resolve()
        if path and file.is_file() and FRONTEND_DIST.resolve() in file.parents:
            return FileResponse(file)
        return FileResponse(FRONTEND_DIST / "index.html")  # React Router handles the URL
