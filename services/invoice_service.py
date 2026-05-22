from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from models.invoice import Invoice, InvoiceStatus
from models.invoice_item import InvoiceItem
from models.sku import SKU
from models.product import Product, ProductStatus
from models.seller import Seller
from schemas.invoice import InvoiceCreate, InvoiceAcceptRequest


async def get_invoice_by_id(db: AsyncSession, invoice_id, seller_id=None) -> Invoice:
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.items))
        .where(Invoice.id == invoice_id)
    )
    invoice = result.scalar_one_or_none()
    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "INVOICE_NOT_FOUND", "message": "Накладная не найдена"},
        )

    if seller_id is not None and invoice.seller_id != seller_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "INVOICE_NOT_FOUND", "message": "Накладная не найдена"},
        )

    return invoice


async def get_invoices(
    db: AsyncSession, seller_id,
    limit: int = 20, offset: int = 0,
    status: str | None = None
) -> dict:
    count_query = select(func.count(Invoice.id)).where(Invoice.seller_id == seller_id)
    if status:
        count_query = count_query.where(Invoice.status == status)
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    query = (
        select(Invoice)
        .options(selectinload(Invoice.items))
        .where(Invoice.seller_id == seller_id)
        .order_by(Invoice.created_at.desc())
    )
    if status:
        query = query.where(Invoice.status == status)
    result = await db.execute(query.limit(limit).offset(offset))

    return {
        "items": result.scalars().all(),
        "total_count": total,
        "limit": limit,
        "offset": offset
    }


async def create_invoice(db: AsyncSession, seller: Seller, data: InvoiceCreate) -> Invoice:
    if not data.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "EMPTY_ITEMS", "message": "Накладная должна содержать хотя бы одну позицию"},
        )

    for item in data.items:
        sku_result = await db.execute(
            select(SKU)
            .join(Product, SKU.product_id == Product.id)
            .where(SKU.id == item.sku_id)
        )
        sku = sku_result.scalar_one_or_none()
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SKU_NOT_FOUND", "message": f"SKU {item.sku_id} не найден"},
            )
        product_result = await db.execute(select(Product).where(Product.id == sku.product_id))
        product = product_result.scalar_one_or_none()
        if not product or product.seller_id != seller.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "ACCESS_DENIED", "message": "Нет доступа к SKU"},
            )
        if product.status != ProductStatus.MODERATED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "SKU_NOT_MODERATED", "message": "SKU товара не прошёл модерацию"},
            )

    invoice = Invoice(seller_id=seller.id, status=InvoiceStatus.CREATED)
    db.add(invoice)
    await db.flush()
    
    for item in data.items:
        db.add(InvoiceItem(invoice_id=invoice.id, sku_id=item.sku_id, quantity=item.quantity))
    await db.commit()
    
    return await get_invoice_by_id(db, invoice.id)


async def accept_invoice(db: AsyncSession, invoice_id, seller: Seller, data: InvoiceAcceptRequest | None = None) -> Invoice:
    invoice = await get_invoice_by_id(db, invoice_id, seller_id=seller.id)
    if invoice.status != InvoiceStatus.CREATED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVOICE_ALREADY_PROCESSED", "message": "Накладная уже обработана"},
        )

    accepted_map = {}
    if data and data.accepted_items:
        for acc in data.accepted_items:
            if acc.accepted_quantity < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"code": "INVALID_QUANTITY", "message": "Количество не может быть отрицательным"},
                )
            accepted_map[acc.invoice_item_id] = acc.accepted_quantity

    for item in invoice.items:
        acc_qty = accepted_map.get(item.id, item.quantity)
        if acc_qty > item.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "QUANTITY_EXCEEDS_REQUESTED",
                    "message": f"Принятое количество для позиции {item.id} превышает заявленное"
                },
            )

    sku_ids = [item.sku_id for item in invoice.items]
    sku_map = {}
    for sku_id in sku_ids:
        result = await db.execute(
            select(SKU).where(SKU.id == sku_id).with_for_update()
        )
        sku = result.scalar_one_or_none()
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "code": "SKU_NOT_FOUND",
                    "message": f"SKU {sku_id} не найден"
                },
            )
        sku_map[sku_id] = sku

    all_full = True
    for item in invoice.items:
        acc_qty = accepted_map.get(item.id, item.quantity)
        item.accepted_quantity = acc_qty
        sku = sku_map[item.sku_id]
        sku.active_quantity += acc_qty
        if acc_qty < item.quantity:
            all_full = False

    invoice.status = InvoiceStatus.ACCEPTED if all_full else InvoiceStatus.PARTIALLY_ACCEPTED
    invoice.accepted_at = datetime.now(timezone.utc)
    invoice.accepted_by = seller.id
    await db.commit()
    return await get_invoice_by_id(db, invoice.id)


async def delete_invoice(db: AsyncSession, invoice_id, seller: Seller):
    invoice = await get_invoice_by_id(db, invoice_id, seller_id=seller.id)
    if invoice.status != InvoiceStatus.CREATED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "CANNOT_DELETE_PROCESSED", "message": "Нельзя удалить обработанную накладную"},
        )
    await db.delete(invoice)
    await db.commit()