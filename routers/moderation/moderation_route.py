from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.dependencies import require_moderation_key
from schemas.events import ModerationEventRequest
from services.moderation_service import handle_moderation_event

moderation_router = APIRouter(
    prefix="/moderation",
    tags=["Moderation Events"],
    dependencies=[Depends(require_moderation_key)],
)


@moderation_router.post(
    "/events",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Прием событий модерации",
)
async def receive_moderation_event(
    data: ModerationEventRequest,
    db: AsyncSession = Depends(get_db),
):
    await handle_moderation_event(db, data)
