import os
import asyncio
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.openapi.utils import get_openapi
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from schemas.error import ErrorResponse
from core.database import engine, Base
from core.config import settings
from routers import routes
from services.outbox_worker import run_outbox_worker

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.ENV == "development" or settings.ENV == "production":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        print("Database tables created")

    stop_event = asyncio.Event()
    outbox_task = asyncio.create_task(run_outbox_worker(stop_event))

    try:
        None
    except Exception as e:
        print(f"Failed to initialize database: {e}")
        if settings.ENV == "production":
            raise

    print("Application started successfully")

    try:
        yield
    finally:
        stop_event.set()
        await outbox_task
        await engine.dispose()


app = FastAPI(
    title="NEO Market", version="1.0.0", lifespan=lifespan, debug=settings.DEBUG
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


for router in routes:
    app.include_router(router, prefix="/api/v1")


# ─────────────────────────────────────────────────────────────────────────────
# Обработчики исключений
# ─────────────────────────────────────────────────────────────────────────────


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """
    Обработчик HTTPException.
    Возвращает ErrorResponse с кодом статуса в виде строки.
    """
    # Маппинг статус-кодов в строковые коды ошибок
    status_code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        500: "INTERNAL_ERROR",
    }
    code = status_code_map.get(exc.status_code, "HTTP_ERROR")

    # Если detail уже содержит код и сообщение — используем их
    if (
        isinstance(exc.detail, dict)
        and "code" in exc.detail
        and "message" in exc.detail
    ):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.detail["code"],
                "message": exc.detail["message"],
                "details": exc.detail.get("details"),
            },
        )

    # Иначе формируем стандартный ответ
    details = None
    if hasattr(exc, "headers") and exc.headers:
        details = dict(exc.headers)

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": code,
            "message": str(exc.detail),
            "details": details,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Обработчик ошибок валидации Pydantic.
    Возвращает ErrorResponse с кодом VALIDATION_ERROR и деталями ошибок.
    """
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "code": "VALIDATION_ERROR",
            "message": "Ошибка валидации запроса",
            "details": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Обработчик необработанных исключений.
    Возвращает ErrorResponse с кодом INTERNAL_ERROR.
    """
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "code": "INTERNAL_ERROR",
            "message": "Внутренняя ошибка сервера",
            "details": None,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Модификация схемы OpenAPI для Swagger
# ─────────────────────────────────────────────────────────────────────────────


def custom_openapi():
    """
    Переопределяем метод openapi() для кастомизации схемы.
    - Удаляем HTTPValidationError и ValidationError из components.schemas
    - Добавляем ErrorResponse как единую модель ошибок
    - Применяем ErrorResponse ко всем статус-кодам ошибок во всех эндпоинтах
    """
    if app.openapi_schema:
        return app.openapi_schema

    # Генерируем стандартную схему
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    if openapi_schema.get("components") and openapi_schema["components"].get("schemas"):
        schemas = openapi_schema["components"]["schemas"]
        schemas.pop("HTTPValidationError", None)
        schemas.pop("ValidationError", None)

        # Добавляем модель ErrorResponse
        schemas["ErrorResponse"] = {
            "title": "ErrorResponse",
            "type": "object",
            "properties": {
                "code": {
                    "title": "Code",
                    "type": "string",
                    "description": "Строковый код ошибки, например VALIDATION_ERROR, NOT_FOUND",
                    "example": "VALIDATION_ERROR",
                },
                "message": {
                    "title": "Message",
                    "type": "string",
                    "description": "Человекочитаемое описание ошибки",
                    "example": "Поле 'title' обязательно",
                },
                "details": {
                    "title": "Details",
                    "type": "object",
                    "description": "Дополнительные данные об ошибке",
                    "nullable": True,
                    "example": {"additionalProp1": {}},
                },
            },
            "required": ["code", "message"],
        }

    # Добавляем ErrorResponse ко всем статус-кодам ошибок во всех эндпоинтах
    error_codes = ["400", "401", "403", "404", "409", "422", "500"]
    for path, path_item in openapi_schema.get("paths", {}).items():
        for method, operation in path_item.items():
            if method in ["get", "post", "put", "patch", "delete"]:
                for code in error_codes:
                    if operation.get("responses", {}).get(code):
                        # Заменяем описание ответа на ссылку на ErrorResponse
                        operation["responses"][code] = {
                            "description": operation["responses"][code].get(
                                "description", "Error"
                            ),
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/ErrorResponse"
                                    }
                                }
                            },
                        }
                    else:
                        # Добавляем ErrorResponse если статус-код отсутствует
                        operation.setdefault("responses", {})[code] = {
                            "description": "Error response",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/ErrorResponse"
                                    }
                                }
                            },
                        }

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


# ─────────────────────────────────────────────────────────────────────────────
# Статические файлы и запуск
# ─────────────────────────────────────────────────────────────────────────────

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.APP_RELOAD,
        log_level=settings.APP_LOG_LEVEL.lower(),
    )
