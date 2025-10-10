from fastapi import FastAPI

from core.config import get_settings
from metadata.api import router as metadata_router


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version=settings.version,
        docs_url='/docs',
        redoc_url='/redoc',
    )

    @application.get('/healthz')
    async def healthz():  # pragma: no cover - trivial endpoint
        return {'status': 'ok'}

    @application.get('/readyz')
    async def readyz():  # pragma: no cover - trivial endpoint
        return {'status': 'ready'}

    application.include_router(metadata_router)
    return application


app = create_app()
