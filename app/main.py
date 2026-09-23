from fastapi import FastAPI
from app.api.routes import router

def create_app() -> FastAPI:
    """Create the Nashr FastAPI application."""
    application = FastAPI(title="Nashr")
    application.include_router(router)
    return application

app = create_app()
