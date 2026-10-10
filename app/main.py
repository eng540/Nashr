import asyncio
import logging
import os

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.adapters.gemini_policy import (
    GeminiOperationError,
    RetryPolicy,
    classify_gemini_error,
    http_status_for,
    resolve_model_chain,
    retry_after_seconds,
)
from app.api.benchmark import benchmark_router
from app.api.control_plane import router as control_plane_router
from app.api.policies import router as policies_router
from app.api.products import router as products_router
from app.api.artifacts import router as generic_artifacts_router
from app.api.routes import router
from app.application.discovery_jobs import recover_stale_jobs, run_discovery_job
from app.application.production_jobs import recover_stale_production_jobs, run_production_job
from app.application.scheduling import process_due_schedule_items, recover_stale_schedule_items

logger = logging.getLogger(__name__)

DEFAULT_SCHEDULE_TRIGGER_INTERVAL_SECONDS = 30.0
MIN_SCHEDULE_TRIGGER_INTERVAL_SECONDS = 5.0


def schedule_trigger_interval() -> float:
    raw = os.getenv("SCHEDULE_TRIGGER_INTERVAL_SECONDS")
    if raw is None:
        return DEFAULT_SCHEDULE_TRIGGER_INTERVAL_SECONDS
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "event=INVALID_SCHEDULE_TRIGGER_INTERVAL value=%r fallback=%s",
            raw,
            DEFAULT_SCHEDULE_TRIGGER_INTERVAL_SECONDS,
        )
        return DEFAULT_SCHEDULE_TRIGGER_INTERVAL_SECONDS
    if value < MIN_SCHEDULE_TRIGGER_INTERVAL_SECONDS:
        logger.warning(
            "event=SCHEDULE_TRIGGER_INTERVAL_TOO_SMALL value=%s minimum=%s fallback=%s",
            value,
            MIN_SCHEDULE_TRIGGER_INTERVAL_SECONDS,
            DEFAULT_SCHEDULE_TRIGGER_INTERVAL_SECONDS,
        )
        return DEFAULT_SCHEDULE_TRIGGER_INTERVAL_SECONDS
    return value


async def run_schedule_trigger() -> None:
    """Continuously wake the durable DB-backed scheduler without queue infrastructure."""
    interval = schedule_trigger_interval()
    while True:
        try:
            processed = await process_due_schedule_items(limit=20)
            if processed:
                logger.info("event=SCHEDULE_TRIGGER_PROCESSED count=%s", processed)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("event=SCHEDULE_TRIGGER_FAILED")
        await asyncio.sleep(interval)


def configure_logging() -> None:
    """Make application INFO events visible (otherwise only warnings show up)."""
    level_name = (os.getenv("LOG_LEVEL") or "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    root.setLevel(level)
    logging.getLogger("app").setLevel(level)


def log_gemini_startup_config() -> None:
    """Log the effective model chain and retry policy once, at startup."""
    raw_model = os.getenv("GEMINI_MODEL")
    if raw_model is not None and not raw_model.strip():
        logger.warning("event=GEMINI_MODEL_EMPTY falling back to the default chain.")
    chain = resolve_model_chain()
    policy = RetryPolicy.from_env()
    logger.info(
        "event=GEMINI_STARTUP_CONFIG models=%s attempts_per_model=%s total_timeout_seconds=%s",
        ",".join(chain),
        policy.max_attempts,
        policy.total_timeout_seconds,
    )


async def gemini_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Map a Gemini provider failure to its real HTTP status instead of a 500."""
    code, retryable = classify_gemini_error(exc)
    status_code = http_status_for(code)
    headers: dict[str, str] = {}
    hint = retry_after_seconds(exc)
    if hint:
        headers["Retry-After"] = str(int(hint))
    logger.warning(
        "event=GEMINI_HTTP_ERROR path=%s status=%s code=%s retryable=%s",
        request.url.path,
        status_code,
        code,
        retryable,
    )
    return JSONResponse(
        status_code=status_code,
        content={"detail": f"Gemini provider error: {code}", "code": code, "retryable": retryable},
        headers=headers,
    )


def register_gemini_error_handlers(application: FastAPI) -> None:
    """Register the shared handler for our own and the SDK's provider errors."""
    application.add_exception_handler(GeminiOperationError, gemini_exception_handler)
    try:
        from google.genai.errors import APIError
    except Exception:  # pragma: no cover - defensive fallback only
        APIError = None  # type: ignore[assignment]
    if APIError is not None:
        application.add_exception_handler(APIError, gemini_exception_handler)


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Recover persisted discovery jobs left RUNNING by a previous process."""
    try:
        recovered = await recover_stale_jobs()
    except Exception:
        logger.exception("event=DISCOVERY_RECOVERY_FAILED")
        recovered = []
    try:
        production_recovered = await recover_stale_production_jobs()
    except Exception:
        logger.exception("event=PRODUCTION_RECOVERY_FAILED")
        production_recovered = []
    try:
        await recover_stale_schedule_items()
    except Exception:
        logger.exception("event=SCHEDULE_RECOVERY_FAILED")
    tasks = [asyncio.create_task(run_discovery_job(job_id)) for job_id in recovered]
    tasks.extend(asyncio.create_task(run_production_job(job_id)) for job_id in production_recovered)
    schedule_task = asyncio.create_task(run_schedule_trigger(), name="nashr-schedule-trigger")
    tasks.append(schedule_task)
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


def create_app() -> FastAPI:
    """Create the Nashr FastAPI application."""
    configure_logging()
    application = FastAPI(title="Nashr", lifespan=lifespan)
    register_gemini_error_handlers(application)
    application.include_router(router)
    application.include_router(control_plane_router)
    application.include_router(policies_router)
    application.include_router(products_router)
    application.include_router(generic_artifacts_router)
    application.include_router(benchmark_router)  # <--- أضف هذا السطر فقط
    log_gemini_startup_config()
    return application


app = create_app()