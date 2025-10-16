from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from core import configure_logging, get_settings, init_observability
from metadata.api import router as metadata_router

origins = [
    'http://localhost',
    'http://localhost:3000',
]


def create_app() -> FastAPI:
    configure_logging()
    init_observability()
    settings = get_settings()

    application = FastAPI(title=settings.app_name, version=settings.version)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
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
