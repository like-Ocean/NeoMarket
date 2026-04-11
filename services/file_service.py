import hashlib
import aiofiles
from pathlib import Path
from datetime import datetime
from fastapi import UploadFile, HTTPException, status
from core.config import settings

ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _get_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _build_unique_filename(original: str, file_hash: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = Path(original).suffix.lower()
    return f"{timestamp}_{file_hash[:16]}{ext}"


async def _validate(file: UploadFile) -> None:
    ext = Path(file.filename).suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Недопустимое расширение. Разрешены: {', '.join(settings.ALLOWED_EXTENSIONS)}",
        )
    if file.content_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Недопустимый MIME-тип. Разрешены только изображения",
        )

    size = 0
    await file.seek(0)
    while chunk := await file.read(1024 * 1024):
        size += len(chunk)
        if size > settings.MAX_FILE_SIZE:
            await file.seek(0)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Файл превышает {settings.MAX_FILE_SIZE // (1024 * 1024)} МБ",
            )
    await file.seek(0)


async def upload_image(file: UploadFile) -> str:
    await _validate(file)
    content = await file.read()
    file_hash = _get_file_hash(content)

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    for existing in upload_dir.iterdir():
        if existing.stem.endswith(file_hash[:16]):
            return f"/uploads/{existing.name}"

    filename = _build_unique_filename(file.filename, file_hash)
    file_path = upload_dir / filename

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    return f"/uploads/{filename}"


def delete_file_from_disk(url: str):
    filename = url.split("/uploads/")[-1]
    file_path = Path(settings.UPLOAD_DIR) / filename
    if file_path.exists():
        file_path.unlink()