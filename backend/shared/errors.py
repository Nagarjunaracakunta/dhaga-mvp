"""One error shape for every endpoint: {"error": {"code": ..., "message": ...}}."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class NotFound(AppError):
    def __init__(self, code: str, message: str):
        super().__init__(code, message, 404)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status, content={"error": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(RequestValidationError)
    async def _invalid_request(_: Request, exc: RequestValidationError):
        problems = [{"field": ".".join(str(p) for p in e["loc"][1:]), "problem": e["msg"]} for e in exc.errors()]
        message = "; ".join(f"{p['field']}: {p['problem']}" for p in problems)
        return JSONResponse(status_code=422, content={"error": {"code": "INVALID_REQUEST", "message": message,
                                                                "details": problems}})
