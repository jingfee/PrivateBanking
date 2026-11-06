import logging
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .config import Settings, get_settings
from .errors import ConfigError
from .db import Base, Database
from .enablebanking import EnableBankingClient
from .sync import sync_all

log = logging.getLogger(__name__)


def default_client_factory(settings: Settings):
    def factory():
        if not settings.eb_app_id:
            return None
        try:
            key = settings.eb_key_path.read_text()
        except FileNotFoundError:
            raise ConfigError(f"Nyckelfilen {settings.eb_key_path} finns inte (montera secrets/eb.pem)")
        except OSError as e:
            raise ConfigError(f"Kan inte läsa nyckelfilen {settings.eb_key_path}: {e.strerror}. "
                              "Containern kör som uid 1000, kör: sudo chown 1000 secrets/eb.pem")
        return EnableBankingClient(settings.eb_app_id, key, settings.eb_api_url)

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
        try:
            client = client_factory()
        except ConfigError as e:
            log.error("sync skipped: %s", e)
            return
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

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error on %s", request.url.path)
        return JSONResponse({"detail": f"Oväntat fel: {type(exc).__name__}: {exc}"}, status_code=500)

    @app.get("/api/health")
    def health():
        try:
            configured, problem = client_factory() is not None, None
        except ConfigError as e:
            configured, problem = False, str(e)
        return {"ok": True, "enable_banking_configured": configured, "problem": problem}

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
