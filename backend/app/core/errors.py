import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ServiceUnavailable(Exception):
    def __init__(self, detail: str = "This service is not configured."):
        self.detail = detail


class NugenFailure(ServiceUnavailable):
    """A safe, categorized provider failure for the guidance API."""

    def __init__(self, detail: str, code: str, http_status: int = 503):
        super().__init__(detail)
        self.code = code
        self.http_status = http_status


class UpstreamError(Exception):
    pass


class SupabaseRequestError(UpstreamError):
    """A rejected Supabase request; details are for server-side diagnosis only."""

    def __init__(self, status_code: int, code: str | None = None):
        self.status_code = status_code
        self.code = code
        super().__init__(f"Supabase status {status_code}, code {code or 'unknown'}")


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceUnavailable)
    async def unavailable(_: Request, exc: ServiceUnavailable):
        content = {"detail": exc.detail, "status": "unavailable"}
        if isinstance(exc, NugenFailure):
            content["code"] = exc.code
        return JSONResponse(status_code=exc.http_status if isinstance(exc, NugenFailure) else 503, content=content)

    @app.exception_handler(UpstreamError)
    async def upstream(_: Request, exc: UpstreamError):
        logging.getLogger("climaguard.upstream").error("upstream_error=%s", exc)
        return JSONResponse(status_code=502, content={"detail": "The data service is temporarily unavailable.", "status": "unavailable"})

    @app.exception_handler(RequestValidationError)
    async def validation(_: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": "Invalid request.", "errors": exc.errors()})

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception):
        logging.getLogger("climaguard.error").exception("Unhandled request error: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})
