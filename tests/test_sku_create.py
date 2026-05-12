import asyncio
import json
import pytest
from uuid import UUID, uuid4
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
        await db_session.execute(
            delete(Product).where(Product.seller_id == seller.id)
        )
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


@pytest.fixture
async def product_factory(db_session, test_context):
    async def _factory(status: ProductStatus = ProductStatus.CREATED) -> Product:
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

    return _factory


@pytest.fixture
async def product(product_factory):
    return await product_factory()


@pytest.fixture
async def valid_sku_payload(product):
    return {
        "product_id": str(product.id),
        "name": "SKU A",
        "price": 1000,
        "discount": 0,
        "cost_price": 500,
        "image": "https://example.com/sku.jpg",
        "article": None,
        "images": [],
        "characteristics": [],
    }


async def test_first_sku_transitions_product_to_on_moderation(
    client, valid_sku_payload, product, db_session
):
    response = await client.post("/api/skus", json=valid_sku_payload)

    assert response.status_code == 201
    await db_session.refresh(product)
    assert product.status == ProductStatus.ON_MODERATION


async def test_first_sku_emits_created_event_to_moderation(
    client, valid_sku_payload, product, db_session, monkeypatch
):
    monkeypatch.setattr(settings, "MODERATION_SERVICE_URL", "http://moderation")

    response = await client.post("/api/skus", json=valid_sku_payload)

    assert response.status_code == 201
    result = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.event_type == "CREATED")
    )
    events = result.scalars().all()
    match_event = None
    match_payload = None
    for event in events:
        payload = json.loads(event.payload)
        if payload.get("product_id") == str(product.id):
            match_event = event
            match_payload = payload
            break

    assert match_event is not None
    assert match_payload is not None
    assert match_event.target_url == "http://moderation/api/v1/events/product"
    assert match_payload["seller_id"] == str(product.seller_id)
    assert match_payload["event"] == "CREATED"
    assert "date" in match_payload


async def test_second_sku_no_state_change(
    client, product_factory, test_context, db_session
):
    product = await product_factory(status=ProductStatus.CREATED)
    existing = SKU(
        id=uuid4(),
        product_id=product.id,
        name="Existing SKU",
        price=1000,
        discount=0,
        cost_price=500,
        image="https://example.com/sku-existing.jpg",
        active_quantity=0,
        reserved_quantity=0,
        article=None,
    )
    db_session.add(existing)
    await db_session.commit()

    payload = {
        "product_id": str(product.id),
        "name": "SKU B",
        "price": 1200,
        "discount": 0,
        "cost_price": 600,
        "image": "https://example.com/sku-b.jpg",
        "article": None,
        "images": [],
        "characteristics": [],
    }
    result_before = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.event_type == "CREATED")
    )
    events_before = result_before.scalars().all()
    before_count = sum(
        1
        for event in events_before
        if json.loads(event.payload).get("product_id") == str(product.id)
    )

    response = await client.post("/api/skus", json=payload)

    assert response.status_code == 201
    await db_session.refresh(product)
    assert product.status == ProductStatus.CREATED

    result_after = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.event_type == "CREATED")
    )
    events_after = result_after.scalars().all()
    after_count = sum(
        1
        for event in events_after
        if json.loads(event.payload).get("product_id") == str(product.id)
    )
    assert after_count == before_count


async def test_add_sku_to_hard_blocked_returns_403(client, product_factory):
    product = await product_factory(status=ProductStatus.HARD_BLOCKED)
    payload = {
        "product_id": str(product.id),
        "name": "SKU A",
        "price": 1000,
        "discount": 0,
        "cost_price": 500,
        "image": "https://example.com/sku.jpg",
        "article": None,
        "images": [],
        "characteristics": [],
    }

    response = await client.post("/api/skus", json=payload)

    assert response.status_code == 403
    assert response.json() == {
        "code": "FORBIDDEN",
        "message": "Cannot add SKU to hard-blocked product",
    }


async def test_product_id_not_exists_returns_404(client, valid_sku_payload):
    payload = valid_sku_payload.copy()
    payload["product_id"] = str(uuid4())

    response = await client.post("/api/skus", json=payload)

    assert response.status_code == 404
    assert response.json() == {
        "code": "NOT_FOUND",
        "message": "Product not found",
    }


async def test_price_zero_returns_400(client, valid_sku_payload):
    payload = valid_sku_payload.copy()
    payload["price"] = 0

    response = await client.post("/api/skus", json=payload)

    assert response.status_code == 400
    assert response.json() == {
        "code": "INVALID_REQUEST",
        "message": "price must be a positive integer (kopecks)",
    }


async def test_cost_price_zero_returns_400(client, valid_sku_payload):
    payload = valid_sku_payload.copy()
    payload["cost_price"] = 0

    response = await client.post("/api/skus", json=payload)

    assert response.status_code == 400
    assert response.json() == {
        "code": "INVALID_REQUEST",
        "message": "cost_price must be a positive integer (kopecks)",
    }


async def test_empty_name_returns_400(client, valid_sku_payload):
    payload = valid_sku_payload.copy()
    payload["name"] = ""

    response = await client.post("/api/skus", json=payload)

    assert response.status_code == 400
    assert response.json() == {
        "code": "INVALID_REQUEST",
        "message": "name is required",
    }


async def test_missing_image_returns_400(client, valid_sku_payload):
    payload = valid_sku_payload.copy()
    payload.pop("image")

    response = await client.post("/api/skus", json=payload)

    assert response.status_code == 400
    assert response.json() == {
        "code": "INVALID_REQUEST",
        "message": "image is required",
    }
