from uuid import UUID
from fastapi import APIRouter, Depends, UploadFile, File, Form, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies import get_current_seller
from models.seller import Seller
from schemas.image import ImageUploadResponse
from services import image_service
from services.file_service import upload_image
from core.database import get_db

upload_router = APIRouter(prefix="/v1", tags=["Images"])

ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024


async def _validate_image_upload(file: UploadFile) -> None:
    if file.content_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="UNSUPPORTED_MEDIA_TYPE",
        )

    size = 0
    await file.seek(0)
    while chunk := await file.read(1024 * 1024):
        size += len(chunk)
        if size > MAX_IMAGE_SIZE_BYTES:
            await file.seek(0)
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="FILE_TOO_LARGE",
            )
    await file.seek(0)


@upload_router.post(
    "/images",
    response_model=ImageUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить изображение",
)
async def upload_image_endpoint(
    file: UploadFile = File(...),
    entity_type: str = Form(...),
    entity_id: UUID = Form(...),
    ordering: int = Form(0),
    db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    normalized_type = entity_type.strip().lower()
    if normalized_type not in {"product", "sku"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="entity_type должен быть product или sku",
        )

    if normalized_type == "product":
        await image_service._get_product_for_seller(
            db=db,
            product_id=entity_id,
            seller_id=current_seller.id,
        )
    else:
        await image_service._get_sku_for_seller(
            db=db,
            sku_id=entity_id,
            seller_id=current_seller.id,
        )

    await _validate_image_upload(file)
    url = await upload_image(file)

    if normalized_type == "product":
        image = await image_service.add_product_image(
            db=db,
            product_id=entity_id,
            seller_id=current_seller.id,
            url=url,
            ordering=ordering,
        )
        return ImageUploadResponse(
            id=image.id,
            url=image.url,
            ordering=image.ordering,
            entity_type="product",
            entity_id=image.product_id,
        )

    image = await image_service.add_sku_image(
        db=db,
        sku_id=entity_id,
        seller_id=current_seller.id,
        url=url,
        ordering=ordering,
    )
    return ImageUploadResponse(
        id=image.id,
        url=image.url,
        ordering=image.ordering,
        entity_type="sku",
        entity_id=image.sku_id,
    )