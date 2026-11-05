import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .config import Settings, get_settings
from .db import Base, Database
from .enablebanking import EnableBankingClient
from .sync import sync_all

log = logging.getLogger(__name__)


def default_client_factory(settings: Settings):
    def factory():
        if not settings.eb_app_id or not settings.eb_key_path.exists():
            return None
        return EnableBankingClient.from_key_file(settings.eb_app_id, settings.eb_key_path, settings.eb_api_url)

    return factory


def migrate(db: Database, database_path: str) -> None:
    if database_path == ":memory:":
        Base.metadata.create_all(db.engine)
        return
    from alembic import command
    from alembic.config import Config

    here = Path(__file__).resolve().parent.parent
    cfg = Config(str(here / "alembic.ini"))
    cfg.set_main_option("script_location", str(here / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(cfg, "head")


def create_app(settings: Settings | None = None, client_factory=None) -> FastAPI:
    settings = settings or get_settings()
    db_path = str(settings.database_path)
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    db = Database(db_path)
    client_factory = client_factory or default_client_factory(settings)

    def scheduled_sync():
        client = client_factory()
        if client is None:
            return
        with db.sessionmaker() as s:
            for r in sync_all(s, client, settings.sync_overlap_days):
                log.info("sync account=%s inserted=%s updated=%s pending=%s error=%s",
                         r.account_id, r.inserted, r.updated, r.pending, r.error)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        migrate(db, db_path)
        scheduler = None
        if settings.scheduler_enabled:
            scheduler = BackgroundScheduler()
            scheduler.add_job(scheduled_sync, "interval", hours=settings.sync_interval_hours,
                              id="sync", max_instances=1, coalesce=True)
            scheduler.start()
        yield
        if scheduler:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="PrivateBanking", lifespan=lifespan)
    app.state.settings = settings
    app.state.db = db
    app.state.client_factory = client_factory
    app.include_router(router)

    @app.get("/api/health")
    def health():
        return {"ok": True, "enable_banking_configured": client_factory() is not None}

    frontend = settings.frontend_dir
    if frontend.exists():
        app.mount("/_app", StaticFiles(directory=frontend / "_app"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            file = (frontend / path).resolve()
            if path and file.is_file() and file.is_relative_to(frontend.resolve()):
                return FileResponse(file)
            return FileResponse(frontend / "index.html")

    return app


logging.basicConfig(level=logging.INFO)
