from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import require_internal_token
from schemas.stock import ReserveItem
from services import stock_service


stock_router = APIRouter(prefix="/stock", tags=["Internal Stock"])


@stock_router.post("/reserve/{order_id}")
async def reserve_stock(
    order_id: UUID, items: list[ReserveItem],
    db: AsyncSession = Depends(get_db)
):
    await stock_service.reserve(db, order_id, [i.model_dump() for i in items])
    return {"status": "reserved"}


@stock_router.post("/reserve/{order_id}/release")
async def release_reservation(
    order_id: UUID, db: AsyncSession = Depends(get_db)
):
    await stock_service.release(db, order_id)
    return {"status": "released"}


@stock_router.post("/reserve/{order_id}/commit")
async def commit_reservation(
    order_id: UUID, db: AsyncSession = Depends(get_db)
):
    await stock_service.commit(db, order_id)
    return {"status": "committed"}