import asyncio
import json
import pytest
from uuid import uuid4
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete, select
from core.config import settings
from core.database import AsyncSessionLocal, Base, engine
from main import app
from models.category import Category
from models.outbox_event import OutboxEvent
from models.product import Product, ProductStatus
from models.processed_event import ProcessedEvent
from models.seller import Seller
from models.invoice_item import InvoiceItem 
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
        await db_session.execute(delete(ProcessedEvent))
        await db_session.execute(delete(InvoiceItem))
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


async def _create_product(db_session, test_context) -> Product:
    product = Product(
        id=uuid4(),
        seller_id=test_context["seller"].id,
        category_id=test_context["category"].id,
        title=f"Product {uuid4()}",
        slug=f"product-{uuid4()}",
        description="",
        status=ProductStatus.MODERATED,
        deleted=False,
        blocked=False,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    return product


async def _create_sku(db_session, product_id, active_qty, reserved_qty=0) -> SKU:
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


async def test_reserve_all_skus_succeeds(client, db_session, test_context, b2c_headers):
    product = await _create_product(db_session, test_context)
    sku1 = await _create_sku(db_session, product.id, active_qty=5)
    sku2 = await _create_sku(db_session, product.id, active_qty=3)

    payload = {
        "idempotency_key": str(uuid4()),
        "order_id": str(uuid4()),
        "items": [
            {"sku_id": str(sku1.id), "quantity": 2},
            {"sku_id": str(sku2.id), "quantity": 1},
        ],
    }

    response = await client.post(
        "/api/v1/inventory/reserve",
        headers=b2c_headers,
        json=payload,
    )

    assert response.status_code == 200
    await db_session.refresh(sku1)
    await db_session.refresh(sku2)
    assert sku1.active_quantity == 3
    assert sku1.reserved_quantity == 2
    assert sku2.active_quantity == 2
    assert sku2.reserved_quantity == 1


async def test_partial_insufficient_stock_returns_409_all_rollback(
    client, db_session, test_context, b2c_headers
):
    product = await _create_product(db_session, test_context)
    sku1 = await _create_sku(db_session, product.id, active_qty=1)
    sku2 = await _create_sku(db_session, product.id, active_qty=0)

    payload = {
        "idempotency_key": str(uuid4()),
        "order_id": str(uuid4()),
        "items": [
            {"sku_id": str(sku1.id), "quantity": 1},
            {"sku_id": str(sku2.id), "quantity": 1},
        ],
    }

    response = await client.post(
        "/api/v1/inventory/reserve",
        headers=b2c_headers,
        json=payload,
    )

    assert response.status_code == 409
    await db_session.refresh(sku1)
    await db_session.refresh(sku2)
    assert sku1.active_quantity == 1
    assert sku1.reserved_quantity == 0
    assert sku2.active_quantity == 0
    assert sku2.reserved_quantity == 0


async def test_idempotent_reserve_returns_200_without_double_deduction(
    client, db_session, test_context, b2c_headers
):
    product = await _create_product(db_session, test_context)
    sku = await _create_sku(db_session, product.id, active_qty=4)
    idempotency_key = str(uuid4())
    order_id = str(uuid4())

    payload = {
        "idempotency_key": idempotency_key,
        "order_id": order_id,
        "items": [{"sku_id": str(sku.id), "quantity": 2}],
    }

    response = await client.post(
        "/api/v1/inventory/reserve",
        headers=b2c_headers,
        json=payload,
    )
    assert response.status_code == 200

    await db_session.refresh(sku)
    assert sku.active_quantity == 2
    assert sku.reserved_quantity == 2

    response = await client.post(
        "/api/v1/inventory/reserve",
        headers=b2c_headers,
        json=payload,
    )
    assert response.status_code == 200

    await db_session.refresh(sku)
    assert sku.active_quantity == 2
    assert sku.reserved_quantity == 2


async def test_sku_out_of_stock_event_emitted(
    client, db_session, test_context, b2c_headers, monkeypatch
):
    monkeypatch.setattr(settings, "B2C_SERVICE_URL", "http://b2c")
    await db_session.execute(delete(OutboxEvent))
    await db_session.commit()

    product = await _create_product(db_session, test_context)
    sku = await _create_sku(db_session, product.id, active_qty=2)

    payload = {
        "idempotency_key": str(uuid4()),
        "order_id": str(uuid4()),
        "items": [{"sku_id": str(sku.id), "quantity": 2}],
    }

    response = await client.post(
        "/api/v1/inventory/reserve",
        headers=b2c_headers,
        json=payload,
    )

    assert response.status_code == 200
    result = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.event_type == "SKU_OUT_OF_STOCK")
    )
    events = result.scalars().all()
    assert len(events) == 1

    payload = json.loads(events[0].payload)
    assert payload["event"] == "SKU_OUT_OF_STOCK"
    assert payload["product_id"] == str(product.id)
    assert payload["sku_ids"] == [str(sku.id)]


async def test_unreserve_restores_quantities(
    client, db_session, test_context, b2c_headers
):
    product = await _create_product(db_session, test_context)
    sku = await _create_sku(db_session, product.id, active_qty=1, reserved_qty=2)

    payload = {
        "order_id": str(uuid4()),
        "items": [{"sku_id": str(sku.id), "quantity": 2}],
    }

    response = await client.post(
        "/api/v1/inventory/unreserve",
        headers=b2c_headers,
        json=payload,
    )

    assert response.status_code == 200
    await db_session.refresh(sku)
    assert sku.active_quantity == 3
    assert sku.reserved_quantity == 0
