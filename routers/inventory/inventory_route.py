from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import require_b2c_key
from schemas.inventory import (
    ReserveRequest, ReserveResponse,
    InventoryOrderRequest, InventoryOrderResponse
)
from services import inventory_service

inventory_router = APIRouter(
    prefix="/inventory",
    tags=["Inventory"],
    dependencies=[Depends(require_b2c_key)],
)


@inventory_router.post("/reserve", response_model=ReserveResponse)
async def reserve_inventory(
    data: ReserveRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await inventory_service.reserve(
        db=db,
        idempotency_key=data.idempotency_key,
        order_id=data.order_id,
        items=[(i.sku_id, i.quantity) for i in data.items],
    )
    if result.get("error"):
        return JSONResponse(status_code=409, content=result["error"])

    return result["response"]


@inventory_router.post("/unreserve", response_model=InventoryOrderResponse)
async def unreserve_inventory(
    data: InventoryOrderRequest,
    db: AsyncSession = Depends(get_db),
):
    return await inventory_service.unreserve(
        db=db,
        order_id=data.order_id,
        items=[(i.sku_id, i.quantity) for i in data.items],
    )


@inventory_router.post("/fulfill", response_model=InventoryOrderResponse)
async def fulfill_inventory(
    data: InventoryOrderRequest,
    db: AsyncSession = Depends(get_db),
):
    return await inventory_service.fulfill(
        db=db,
        order_id=data.order_id,
        items=[(i.sku_id, i.quantity) for i in data.items],
    )
