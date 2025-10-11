from fastapi import FastAPI

from core import configure_logging, get_settings
from metadata.api import router as metadata_router


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    application = FastAPI(title=settings.app_name, version=settings.version)

    @application.get('/healthz')
    async def healthz():  # pragma: no cover - trivial endpoint
        return {'status': 'ok'}

    @application.get('/readyz')
    async def readyz():  # pragma: no cover - trivial endpoint
        return {'status': 'ready'}

    application.include_router(metadata_router)
    return application


app = create_app()
