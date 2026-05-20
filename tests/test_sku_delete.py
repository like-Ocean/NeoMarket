import asyncio
import json
import pytest
from uuid import uuid4
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete, select
from core.config import settings
from core.database import AsyncSessionLocal, Base, engine
from core.dependencies import get_current_seller
from main import app
from models.category import Category
from models.outbox_event import OutboxEvent
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
        await db_session.execute(delete(OutboxEvent))
        await db_session.execute(delete(SKU))
        await db_session.execute(delete(Product).where(Product.seller_id == seller.id))
        await db_session.execute(delete(Category).where(Category.id == category.id))
        await db_session.execute(delete(Seller).where(Seller.id == seller.id))
        await db_session.commit()


@pytest.fixture
async def client(test_context):
    async def _override_get_current_seller():
        return test_context["seller"]

    app.dependency_overrides[get_current_seller] = _override_get_current_seller
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_current_seller, None)


async def _create_product(db_session, test_context, status: ProductStatus) -> Product:
    product = Product(
        id=uuid4(),
        seller_id=test_context["seller"].id,
        category_id=test_context["category"].id,
        title="Test product",
        slug=f"test-product-{uuid4()}",
        description="",
        status=status,
        deleted=False,
        blocked=False,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    return product


async def _create_sku(db_session, product_id, active_qty=0, reserved_qty=0) -> SKU:
    sku = SKU(
        id=uuid4(),
        product_id=product_id,
        name="SKU",
        price=1000,
        discount=0,
        cost_price=500,
        active_quantity=active_qty,
        reserved_quantity=reserved_qty,
        article=None,
    )
    db_session.add(sku)
    await db_session.commit()
    await db_session.refresh(sku)
    return sku


async def test_delete_sku_succeeds(client, db_session, test_context):
    product = await _create_product(db_session, test_context, ProductStatus.CREATED)
    sku = await _create_sku(db_session, product.id)

    response = await client.delete(f"/api/v1/skus/{sku.id}")

    assert response.status_code == 204
    result = await db_session.execute(select(SKU).where(SKU.id == sku.id))
    assert result.scalar_one_or_none() is None


async def test_delete_sku_with_active_reserves_returns_409(
    client, db_session, test_context
):
    product = await _create_product(db_session, test_context, ProductStatus.CREATED)
    sku = await _create_sku(db_session, product.id, reserved_qty=2)

    response = await client.delete(f"/api/v1/skus/{sku.id}")

    assert response.status_code == 409


async def test_last_sku_on_moderation_transitions_product_to_created(
    client, db_session, test_context, monkeypatch
):
    monkeypatch.setattr(settings, "MODERATION_SERVICE_URL", "http://moderation")
    await db_session.execute(delete(OutboxEvent))
    await db_session.commit()

    product = await _create_product(db_session, test_context, ProductStatus.ON_MODERATION)
    sku = await _create_sku(db_session, product.id)

    response = await client.delete(f"/api/v1/skus/{sku.id}")

    assert response.status_code == 204
    await db_session.refresh(product)
    assert product.status == ProductStatus.CREATED

    result = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.event_type == "DELETED")
    )
    events = result.scalars().all()
    assert len(events) == 1

    event = events[0]
    assert event.target_url == "http://moderation/api/v1/events/product"
    payload = json.loads(event.payload)
    assert payload["product_id"] == str(product.id)
    assert payload["seller_id"] == str(product.seller_id)
    assert payload["event"] == "DELETED"
    assert "date" in payload


async def test_delete_sku_hard_blocked_product_returns_403(
    client, db_session, test_context
):
    product = await _create_product(db_session, test_context, ProductStatus.HARD_BLOCKED)
    sku = await _create_sku(db_session, product.id)

    response = await client.delete(f"/api/v1/skus/{sku.id}")

    assert response.status_code == 403


async def test_sku_out_of_stock_event_on_moderated_product(
    client, db_session, test_context, monkeypatch
):
    monkeypatch.setattr(settings, "B2C_SERVICE_URL", "http://b2c")
    await db_session.execute(delete(OutboxEvent))
    await db_session.commit()

    product = await _create_product(db_session, test_context, ProductStatus.MODERATED)
    sku = await _create_sku(db_session, product.id, active_qty=3)

    response = await client.delete(f"/api/v1/skus/{sku.id}")

    assert response.status_code == 204
    result = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.event_type == "SKU_OUT_OF_STOCK")
    )
    events = result.scalars().all()
    assert len(events) == 1

    payload = json.loads(events[0].payload)
    assert payload["event"] == "SKU_OUT_OF_STOCK"
    assert payload["product_id"] == str(product.id)
    assert payload["sku_ids"] == [str(sku.id)]
