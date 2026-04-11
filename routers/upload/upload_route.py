from fastapi import APIRouter, Depends, UploadFile, File, status
from pydantic import BaseModel

from core.dependencies import get_current_seller
from services.file_service import upload_image

upload_router = APIRouter(prefix="/upload", tags=["Upload"])


class UploadResponse(BaseModel):
    url: str


@upload_router.post(
    "/image", response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить изображение",
)
async def upload_image_endpoint(
    file: UploadFile = File(...), _=Depends(get_current_seller)
):
    url = await upload_image(file)
    
    return UploadResponse(url=url)