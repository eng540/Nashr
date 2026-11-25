import asyncio
import logging
import math
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
from app.api.legal import router as legal_router
from app.api.auth import AuthMiddleware, router as auth_router
from app.api.benchmark import benchmark_router
from app.api.control_plane import router as control_plane_router
from app.api.policies import router as policies_router
from app.api.products import router as products_router
from app.api.artifacts import router as generic_artifacts_router
from app.api.library_import import router as library_import_router
from app.api.connections import router as connections_router
from app.api.facebook_page_connections import router as facebook_page_connections_router
from app.api.tiktok_connections import router as tiktok_connections_router
from app.api.facebook_reel_execution import router as facebook_reel_execution_router
from app.api.instagram_connections import router as instagram_connections_router
from app.api.instagram_execution import router as instagram_execution_router
from app.api.instagram_page_connections import router as instagram_page_connections_router
from app.api.instagram_direct_connections import router as instagram_direct_connections_router
from app.api.youtube_reviews import router as youtube_reviews_router
from app.api.facebook_reviews import router as facebook_reviews_router
from app.api.publishing_queue import router as publishing_queue_router
from app.api.platform_operations import router as platform_operations_router
from app.api.routes import router
from app.application.discovery_jobs import recover_stale_jobs, run_discovery_job
from app.application.production_jobs import recover_stale_production_jobs, run_production_job
from app.application.scheduling import process_due_schedule_items, recover_stale_schedule_items

from app.infrastructure.connection_logging import install as install_connection_log_safety
install_connection_log_safety()

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
    if not math.isfinite(value) or value < MIN_SCHEDULE_TRIGGER_INTERVAL_SECONDS:
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
            try:
                from app.application.tiktok_oauth import cleanup_expired_flows
                await cleanup_expired_flows()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Do not include candidate data or provider exceptions in logs.
                logger.warning("event=TIKTOK_TEMPORARY_FLOW_CLEANUP_FAILED")
            try:
                from app.application.instagram_runtime import process_approved
                await process_approved()
                from app.application.facebook_reel_runtime import process_approved as process_facebook_reels
                await process_facebook_reels()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("event=INSTAGRAM_TRIGGER_FAILED")
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
    # httpx INFO request logs include full URLs. Telegram Bot API URLs embed
    # the bot token in the path, so never emit those request lines.
    logging.getLogger("httpx").setLevel(max(level, logging.WARNING))
    # httpcore DEBUG logs request target paths, which also include Telegram's token.
    logging.getLogger("httpcore").setLevel(max(level, logging.WARNING))


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
    application.add_middleware(AuthMiddleware)

    @application.get("/", include_in_schema=False)
    async def root_redirect():
        from fastapi.responses import RedirectResponse

        return RedirectResponse("/bank", status_code=303)

    @application.get("/tiktokQDsoHAsAIEswE2q0vxreoi4iWCJbhDsS.txt", include_in_schema=False)
    async def tiktok_domain_verification():
        from pathlib import Path
        from fastapi.responses import Response
        proof = (Path(__file__).parent / "static" / "tiktokQDsoHAsAIEswE2q0vxreoi4iWCJbhDsS.txt").read_bytes().rstrip(b"\n")
        return Response(proof, media_type="text/plain")

    @application.get("/tiktokePPmBzm3Ej1QWBVM7rVXy8eiIbCCGpJj.txt", include_in_schema=False)
    async def tiktok_sandbox_domain_verification():
        from pathlib import Path
        from fastapi.responses import Response
        proof = (Path(__file__).parent / "static" / "tiktokePPmBzm3Ej1QWBVM7rVXy8eiIbCCGpJj.txt").read_bytes().rstrip(b"\n")
        return Response(proof, media_type="text/plain")

    from app.api.workspace_progress import router as workspace_progress_router
    application.include_router(workspace_progress_router)
    application.include_router(auth_router)
    application.include_router(legal_router)
    register_gemini_error_handlers(application)
    application.include_router(router)
    application.include_router(control_plane_router)
    application.include_router(policies_router)
    application.include_router(products_router)
    application.include_router(generic_artifacts_router)
    application.include_router(library_import_router)
    application.include_router(publishing_queue_router)
    application.include_router(platform_operations_router)
    application.include_router(facebook_page_connections_router)
    application.include_router(facebook_reel_execution_router)
    application.include_router(tiktok_connections_router)
    application.include_router(instagram_connections_router)
    application.include_router(instagram_execution_router)
    application.include_router(instagram_page_connections_router)
    application.include_router(instagram_direct_connections_router)
    application.include_router(youtube_reviews_router)
    application.include_router(facebook_reviews_router)
    application.include_router(connections_router)
    from fastapi.exceptions import RequestValidationError
    from fastapi.exception_handlers import request_validation_exception_handler
    from fastapi.responses import JSONResponse
    @application.exception_handler(RequestValidationError)
    async def secret_validation(request,exc):
        if request.url.path.startswith('/api/connections'):
            return JSONResponse({'detail':'حقول الربط غير صالحة أو ناقصة. لم نحفظ الأسرار.'},status_code=422,headers={'Cache-Control':'no-store'})
        return await request_validation_exception_handler(request,exc)

    application.include_router(benchmark_router)  # <--- أضف هذا السطر فقط
    log_gemini_startup_config()
    return application


app = create_app()
