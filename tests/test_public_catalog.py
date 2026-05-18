import asyncio
import pytest
from uuid import uuid4
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete

from core.config import settings
from core.database import AsyncSessionLocal, Base, engine
from main import app
from models.category import Category
from models.product import Product, ProductStatus
from models.seller import Seller
from models.sku import SKU

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture(scope="session", autouse=True)
async def init_db():
    last_error = None
    for _ in range(10):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            break
        except Exception as exc:
            last_error = exc
            await asyncio.sleep(1)
    if last_error:
        raise last_error
    yield
    await engine.dispose()


@pytest.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session


@pytest.fixture
async def test_context(db_session):
    seller = Seller(
        id=uuid4(),
        email=f"seller-{uuid4()}@example.com",
        password_hash="fake_hash",
        first_name="Test",
        last_name="Seller",
        company_name="Test Company",
        inn=str(uuid4()).replace("-", "")[:12],
    )
    category = Category(
        id=uuid4(),
        name=f"Category {uuid4()}",
        parent_id=None,
    )
    db_session.add_all([seller, category])
    await db_session.commit()
    await db_session.refresh(seller)
    await db_session.refresh(category)

    try:
        yield {"seller": seller, "category": category}
    finally:
        await db_session.execute(delete(SKU))
        await db_session.execute(delete(Product).where(Product.seller_id == seller.id))
        await db_session.execute(delete(Category).where(Category.id == category.id))
        await db_session.execute(delete(Seller).where(Seller.id == seller.id))
        await db_session.commit()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def b2c_headers(monkeypatch):
    monkeypatch.setattr(settings, "B2C_SERVICE_KEY", "test-b2c-key")
    return {"X-Service-Key": "test-b2c-key"}


async def _create_product(
    db_session,
    test_context,
    status: ProductStatus,
    deleted: bool = False,
) -> Product:
    product = Product(
        id=uuid4(),
        seller_id=test_context["seller"].id,
        category_id=test_context["category"].id,
        title=f"Product {uuid4()}",
        slug=f"product-{uuid4()}",
        description="",
        status=status,
        deleted=deleted,
        blocked=False,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    return product


async def _create_sku(
    db_session,
    product_id,
    active_quantity: int,
    reserved_quantity: int = 0,
) -> SKU:
    sku = SKU(
        id=uuid4(),
        product_id=product_id,
        name="SKU",
        price=1000,
        discount=0,
        cost_price=500,
        active_quantity=active_quantity,
        reserved_quantity=reserved_quantity,
        article=None,
    )
    db_session.add(sku)
    await db_session.commit()
    await db_session.refresh(sku)
    return sku


async def test_catalog_returns_moderated_in_stock_products(
    client, db_session, test_context, b2c_headers
):
    visible = await _create_product(db_session, test_context, ProductStatus.MODERATED)
    await _create_sku(db_session, visible.id, active_quantity=3)

    no_stock = await _create_product(db_session, test_context, ProductStatus.MODERATED)
    await _create_sku(db_session, no_stock.id, active_quantity=0)

    deleted = await _create_product(db_session, test_context, ProductStatus.MODERATED, deleted=True)
    await _create_sku(db_session, deleted.id, active_quantity=5)

    blocked = await _create_product(db_session, test_context, ProductStatus.BLOCKED)
    await _create_sku(db_session, blocked.id, active_quantity=5)

    response = await client.get("/api/v1/public/products", headers=b2c_headers)

    assert response.status_code == 200
    items = response.json()["items"]
    item_ids = {item["id"] for item in items}
    assert str(visible.id) in item_ids
    assert str(no_stock.id) not in item_ids
    assert str(deleted.id) not in item_ids
    assert str(blocked.id) not in item_ids


async def test_catalog_excludes_hard_blocked(
    client, db_session, test_context, b2c_headers
):
    hard_blocked = await _create_product(db_session, test_context, ProductStatus.HARD_BLOCKED)
    await _create_sku(db_session, hard_blocked.id, active_quantity=5)

    response = await client.get("/api/v1/public/products", headers=b2c_headers)

    assert response.status_code == 200
    item_ids = {item["id"] for item in response.json()["items"]}
    assert str(hard_blocked.id) not in item_ids


async def test_catalog_missing_service_key_returns_401(client):
    response = await client.get("/api/v1/public/products")

    assert response.status_code == 401


async def test_catalog_response_has_no_cost_price(
    client, db_session, test_context, b2c_headers
):
    product = await _create_product(db_session, test_context, ProductStatus.MODERATED)
    await _create_sku(db_session, product.id, active_quantity=2, reserved_quantity=1)

    response = await client.get(
        f"/api/v1/public/products/{product.id}",
        headers=b2c_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert "skus" in data and len(data["skus"]) == 1
    sku = data["skus"][0]
    assert "cost_price" not in sku
    assert "reserved_quantity" not in sku


async def test_batch_ids_returns_visible_subset(
    client, db_session, test_context, b2c_headers
):
    visible = await _create_product(db_session, test_context, ProductStatus.MODERATED)
    await _create_sku(db_session, visible.id, active_quantity=4)

    hidden = await _create_product(db_session, test_context, ProductStatus.MODERATED)
    await _create_sku(db_session, hidden.id, active_quantity=0)

    hard_blocked = await _create_product(db_session, test_context, ProductStatus.HARD_BLOCKED)
    await _create_sku(db_session, hard_blocked.id, active_quantity=2)

    response = await client.post(
        "/api/v1/public/products/batch",
        headers=b2c_headers,
        json={
            "product_ids": [
                str(visible.id),
                str(hidden.id),
                str(hard_blocked.id),
            ]
        },
    )

    assert response.status_code == 200
    items = response.json()
    item_ids = {item["id"] for item in items}
    assert item_ids == {str(visible.id)}
