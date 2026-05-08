import os
import asyncio
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from core.database import engine, Base
from core.config import settings
from routers import routes
from services.outbox_worker import run_outbox_worker
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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
    title="NEO Market", version="1.0.0",
    lifespan=lifespan, debug=settings.DEBUG
)
# удалить 
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    for err in exc.errors():
        # Отсутствует category_id
        if err["loc"][-1] == "category_id" and err["type"] == "missing":
            return JSONResponse(
                status_code=400,
                content={"code": "INVALID_REQUEST", "message": "Requires a category_id"}
            )
        # Невалидный UUID (строка, не UUID)
        if err["loc"][-1] == "category_id" and err["type"] == "uuid_parsing":
            return JSONResponse(
                status_code=400,
                content={"code": "INVALID_REQUEST", "message": "category_id must be a valid UUID"}
            )
        # Отсутствует images
        if err["loc"][-1] == "images" and err["type"] == "missing":
            return JSONResponse(
                status_code=400,
                content={"code": "INVALID_REQUEST", "message": "At least one image is required"}
            )

    # Все остальные ошибки – стандартный ответ 422
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()}
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=['http://localhost:5173'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


for router in routes:
    app.include_router(router, prefix="/api")

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.APP_RELOAD,
        log_level=settings.APP_LOG_LEVEL.lower()
    )
