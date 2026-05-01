from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import require_b2c_key
from schemas.inventory import InventoryRequest
from services import inventory_service

inventory_router = APIRouter(prefix="", tags=["Inventory"])


@inventory_router.post("/reserve")
async def reserve_inventory(
    data: InventoryRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_b2c_key),
):
    await inventory_service.reserve(db, [(i.sku_id, i.quantity) for i in data.items])


@inventory_router.post("/unreserve")
async def unreserve_inventory(
    data: InventoryRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_b2c_key),
):
    await inventory_service.unreserve(db, [(i.sku_id, i.quantity) for i in data.items])


@inventory_router.post("/fulfill")
async def fulfill_inventory(
    data: InventoryRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_b2c_key),
):
    await inventory_service.fulfill(db, [(i.sku_id, i.quantity) for i in data.items])
