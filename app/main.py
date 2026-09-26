import asyncio

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.application.discovery_jobs import recover_stale_jobs, run_discovery_job


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Recover persisted discovery jobs left RUNNING by a previous process."""
    recovered = await recover_stale_jobs()
    tasks = [asyncio.create_task(run_discovery_job(job_id)) for job_id in recovered]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


def create_app() -> FastAPI:
    """Create the Nashr FastAPI application."""
    application = FastAPI(title="Nashr", lifespan=lifespan)
    application.include_router(router)
    return application


app = create_app()
