from uuid import UUID
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from core.database import get_db
from core.dependencies import get_current_seller
from models.seller import Seller
from schemas.invoice import (
    InvoiceCreate, InvoiceResponse,
    InvoicePaginatedResponse,
    InvoiceAcceptRequest
)
from services import invoice_service

invoice_router = APIRouter(prefix="/invoices", tags=["Invoices"])


@invoice_router.get("", response_model=InvoicePaginatedResponse, summary="Список накладных")
async def get_invoices(
    limit: int = 20, offset: int = 0,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller)
):
    return await invoice_service.get_invoices(
        db=db,
        seller_id=current_seller.id,
        limit=limit,
        offset=offset,
        status=status
    )


@invoice_router.get("/{invoice_id}", response_model=InvoiceResponse, summary="Получить накладную")
async def get_invoice(
    invoice_id: UUID, db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller)
):
    return await invoice_service.get_invoice_by_id(
        db, invoice_id, seller_id=current_seller.id
    )


@invoice_router.post(
    "", response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать накладную"
)
async def create_invoice(
    data: InvoiceCreate, db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller)
):
    return await invoice_service.create_invoice(db, current_seller, data)


@invoice_router.post(
    "/{invoice_id}/accept",
    response_model=InvoiceResponse,
    summary="Принять накладную — пополнить остатки SKU"
)
async def accept_invoice(
    invoice_id: UUID,
    data: InvoiceAcceptRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    return await invoice_service.accept_invoice(db, invoice_id, current_seller, data)


@invoice_router.delete(
    "/{invoice_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить накладную (только со статусом CREATED)"
)
async def delete_invoice(
    invoice_id: UUID, db: AsyncSession = Depends(get_db),
    current_seller: Seller = Depends(get_current_seller),
):
    await invoice_service.delete_invoice(db, invoice_id, current_seller)