from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import require_b2c_key
from schemas.inventory import InventoryRequest, InventoryOrderRequest
from services import inventory_service

inventory_router = APIRouter(
    prefix="/v1", tags=["Inventory"],
    dependencies=[Depends(require_b2c_key)],
)


@inventory_router.post("/reserve")
async def reserve_inventory(
    data: InventoryRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await inventory_service.reserve(
        db, data.idempotency_key,
        [(i.sku_id, i.quantity) for i in data.items],
    )
    if not result["reserved"]:
        return JSONResponse(status_code=409, content=result)
    
    return result


@inventory_router.post("/unreserve")
async def unreserve_inventory(
    data: InventoryOrderRequest,
    db: AsyncSession = Depends(get_db),
):
    await inventory_service.unreserve(
        db, data.order_id,
        [(i.sku_id, i.quantity) for i in data.items],
    )


@inventory_router.post("/fulfill")
async def fulfill_inventory(
    data: InventoryOrderRequest,
    db: AsyncSession = Depends(get_db),
):
    await inventory_service.fulfill(
        db, data.order_id,
        [(i.sku_id, i.quantity) for i in data.items],
    )
