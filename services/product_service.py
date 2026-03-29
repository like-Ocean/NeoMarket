from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from models.category import Category
from models.product import Product
from models.product_characteristic import ProductCharacteristic
from models.product_image import ProductImage
from models.seller import Seller
from schemas.product import ProductCreate, ProductUpdate


async def get_product_by_id(db: AsyncSession, product_id) -> Product | None:
	result = await db.execute(
		select(Product)
		.options(
			selectinload(Product.images),
			selectinload(Product.characteristics),
			selectinload(Product.skus),
		)
		.where(Product.id == product_id)
	)
	return result.scalar_one_or_none()


async def get_products(db: AsyncSession, limit: int = 20, offset: int = 0) -> dict:
	total_result = await db.execute(select(func.count(Product.id)))
	total = total_result.scalar_one()

	result = await db.execute(
		select(Product)
		.order_by(Product.created_at.desc())
		.limit(limit)
		.offset(offset)
	)

	return {
		"total": total,
		"items": result.scalars().all(),
	}


async def create_product(db: AsyncSession, seller: Seller, data: ProductCreate) -> Product:
	category_result = await db.execute(
		select(Category).where(Category.id == data.category_id)
	)
	category = category_result.scalar_one_or_none()
	if not category:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Категория не найдена",
		)

	product = Product(
		seller_id=seller.id,
		category_id=data.category_id,
		title=data.title,
		description=data.description,
	)
	db.add(product)
	await db.flush()

	for image in data.images:
		db.add(ProductImage(
			product_id=product.id,
			url=image.url,
			ordering=image.ordering,
		))

	for characteristic in data.characteristics:
		db.add(ProductCharacteristic(
			product_id=product.id,
			name=characteristic.name,
			value=characteristic.value,
		))

	await db.commit()
	return await get_product_by_id(db, product.id)


async def update_product(
	db: AsyncSession,
	product_id,
	seller: Seller,
	data: ProductUpdate,
) -> Product:
	product = await get_product_by_id(db, product_id)
	if not product:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Товар не найден",
		)

	if product.seller_id != seller.id:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="Нет доступа к товару",
		)

	if data.category_id is not None:
		category_result = await db.execute(
			select(Category).where(Category.id == data.category_id)
		)
		category = category_result.scalar_one_or_none()
		if not category:
			raise HTTPException(
				status_code=status.HTTP_404_NOT_FOUND,
				detail="Категория не найдена",
			)

	for field, value in data.model_dump(exclude_unset=True).items():
		setattr(product, field, value)

	await db.commit()
	return await get_product_by_id(db, product.id)


async def delete_product(db: AsyncSession, product_id, seller: Seller) -> None:
	product = await get_product_by_id(db, product_id)
	if not product:
		raise HTTPException(
			status_code=status.HTTP_404_NOT_FOUND,
			detail="Товар не найден",
		)

	if product.seller_id != seller.id:
		raise HTTPException(
			status_code=status.HTTP_403_FORBIDDEN,
			detail="Нет доступа к товару",
		)

	await db.delete(product)
	await db.commit()
