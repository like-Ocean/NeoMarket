from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from models.invoice import Invoice, InvoiceStatus
from models.invoice_item import InvoiceItem
from models.sku import SKU
from models.product import Product
from models.seller import Seller
from schemas.invoice import InvoiceCreate


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
            detail="Накладная не найдена",
        )

    if seller_id is not None and invoice.seller_id != seller_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Нет доступа к накладной",
        )

    return invoice


async def get_invoices(db: AsyncSession, seller_id, limit: int = 20, offset: int = 0) -> dict:
    total_result = await db.execute(
        select(func.count(Invoice.id)).where(Invoice.seller_id == seller_id)
    )
    total = total_result.scalar_one()
    result = await db.execute(
        select(Invoice)
        .options(selectinload(Invoice.items))
        .where(Invoice.seller_id == seller_id)
        .order_by(Invoice.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    return {
        "total": total,
        "items": result.scalars().all(),
    }


async def create_invoice(db: AsyncSession, seller: Seller, data: InvoiceCreate) -> Invoice:
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
                detail=f"SKU {item.sku_id} не найден",
            )

        product_result = await db.execute(
            select(Product).where(Product.id == sku.product_id)
        )
        product = product_result.scalar_one_or_none()
        if not product or product.seller_id != seller.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"SKU {item.sku_id} не принадлежит вашим товарам",
            )

    invoice = Invoice(
        seller_id=seller.id,
        status=InvoiceStatus.CREATED,
    )
    db.add(invoice)
    await db.flush()

    for item in data.items:
        db.add(InvoiceItem(
            invoice_id=invoice.id,
            sku_id=item.sku_id,
            quantity=item.quantity,
        ))

    await db.commit()
    
    return await get_invoice_by_id(db, invoice.id)


async def accept_invoice(db: AsyncSession, invoice_id, seller: Seller) -> Invoice:
    invoice = await get_invoice_by_id(db, invoice_id, seller_id=seller.id)
    if invoice.status == InvoiceStatus.ACCEPTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Накладная уже принята",
        )

    for item in invoice.items:
        sku_result = await db.execute(
            select(SKU).where(SKU.id == item.sku_id)
        )
        sku = sku_result.scalar_one_or_none()
        if not sku:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"SKU {item.sku_id} не найден",
            )

        sku.stock_quantity += item.quantity

    invoice.status = InvoiceStatus.ACCEPTED
    await db.commit()

    return await get_invoice_by_id(db, invoice.id)


async def delete_invoice(db: AsyncSession, invoice_id, seller: Seller):
    invoice = await get_invoice_by_id(db, invoice_id, seller_id=seller.id)

    if invoice.status == InvoiceStatus.ACCEPTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Нельзя удалить принятую накладную",
        )

    await db.delete(invoice)
    
    await db.commit()