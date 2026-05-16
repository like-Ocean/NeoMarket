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
from models.sku_image import SKUImage
from models.sku_characteristic import SKUCharacteristic

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
        await db_session.execute(delete(SKUImage))
        await db_session.execute(delete(SKUCharacteristic))
        await db_session.execute(delete(SKU))
        await db_session.execute(delete(OutboxEvent))
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
        "article": None,
        "images": [],
        "characteristics": [],
    }


async def test_first_sku_transitions_product_to_on_moderation(
    client, valid_sku_payload, product, db_session
):
    response = await client.post("/api/v1/skus", json=valid_sku_payload)

    assert response.status_code == 201
    await db_session.refresh(product)
    assert product.status == ProductStatus.ON_MODERATION


async def test_first_sku_emits_created_event_to_moderation(
    client, valid_sku_payload, product, db_session, monkeypatch
):
    monkeypatch.setattr(settings, "MODERATION_SERVICE_URL", "http://moderation")

    response = await client.post("/api/v1/skus", json=valid_sku_payload)

    assert response.status_code == 201
    result = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.event_type == "CREATED")
    )
    events = result.scalars().all()
    assert len(events) == 1

    event = events[0]
    assert event.target_url == "http://moderation/api/v1/events/product"

    payload = json.loads(event.payload)
    assert payload["product_id"] == str(product.id)
    assert payload["seller_id"] == str(product.seller_id)
    assert payload["event"] == "CREATED"
    assert "date" in payload


async def test_second_sku_no_state_change(
    client, valid_sku_payload, product, db_session
):
    await db_session.execute(delete(OutboxEvent))

    sku = SKU(
        id=uuid4(),
        product_id=product.id,
        name="Existing SKU",
        price=900,
        discount=0,
        cost_price=None,
        active_quantity=0,
        reserved_quantity=0,
        article=None,
    )
    db_session.add(sku)
    await db_session.commit()

    response = await client.post("/api/v1/skus", json=valid_sku_payload)

    assert response.status_code == 201
    await db_session.refresh(product)
    assert product.status == ProductStatus.CREATED

    result = await db_session.execute(select(OutboxEvent))
    assert result.scalars().all() == []


async def test_add_sku_to_hard_blocked_returns_403(client, valid_sku_payload, product_factory):
    hard_blocked_product = await product_factory(status=ProductStatus.HARD_BLOCKED)
    payload = dict(valid_sku_payload)
    payload["product_id"] = str(hard_blocked_product.id)

    response = await client.post("/api/v1/skus", json=payload)

    assert response.status_code == 403


async def test_add_sku_product_not_found_returns_404(client, valid_sku_payload):
    payload = dict(valid_sku_payload)
    payload["product_id"] = str(uuid4())

    response = await client.post("/api/v1/skus", json=payload)

    assert response.status_code == 404


async def test_add_sku_wrong_seller_returns_404(client, valid_sku_payload, db_session, test_context):
    other_seller = Seller(
        id=uuid4(),
        email=f"other-{uuid4()}@example.com",
        password_hash="fake_hash",
        first_name="Other",
        last_name="Seller",
        company_name="Other Company",
        inn=str(uuid4()).replace("-", "")[:12],
    )
    db_session.add(other_seller)
    await db_session.commit()
    await db_session.refresh(other_seller)

    product = Product(
        id=uuid4(),
        seller_id=other_seller.id,
        category_id=test_context["category"].id,
        title="Other product",
        slug=f"other-product-{uuid4()}",
        description="",
        status=ProductStatus.CREATED,
        deleted=False,
        blocked=False,
    )
    db_session.add(product)
    await db_session.commit()

    payload = dict(valid_sku_payload)
    payload["product_id"] = str(product.id)

    response = await client.post("/api/v1/skus", json=payload)

    assert response.status_code == 404

    await db_session.execute(delete(Product).where(Product.id == product.id))
    await db_session.execute(delete(Seller).where(Seller.id == other_seller.id))
    await db_session.commit()


async def test_add_sku_to_on_moderation_returns_403(client, valid_sku_payload, product_factory):
    on_moderation_product = await product_factory(status=ProductStatus.ON_MODERATION)
    payload = dict(valid_sku_payload)
    payload["product_id"] = str(on_moderation_product.id)

    response = await client.post("/api/v1/skus", json=payload)

    assert response.status_code == 403


async def test_add_sku_with_duplicate_article_returns_409(
    client, valid_sku_payload, product, db_session
):
    existing = SKU(
        id=uuid4(),
        product_id=product.id,
        name="Existing SKU",
        price=900,
        discount=0,
        cost_price=None,
        active_quantity=0,
        reserved_quantity=0,
        article="ART-1",
    )
    db_session.add(existing)
    await db_session.commit()

    payload = dict(valid_sku_payload)
    payload["article"] = "ART-1"

    response = await client.post("/api/v1/skus", json=payload)

    assert response.status_code == 409


async def test_add_sku_creates_images_and_characteristics(
    client, valid_sku_payload, db_session
):
    payload = dict(valid_sku_payload)
    payload["images"] = [{"url": "http://img/1.jpg", "ordering": 1}]
    payload["characteristics"] = [{"name": "Color", "value": "Black"}]

    response = await client.post("/api/v1/skus", json=payload)

    assert response.status_code == 201
    sku_id = UUID(response.json()["id"])

    image_result = await db_session.execute(
        select(SKUImage).where(SKUImage.sku_id == sku_id)
    )
    characteristic_result = await db_session.execute(
        select(SKUCharacteristic).where(SKUCharacteristic.sku_id == sku_id)
    )

    assert len(image_result.scalars().all()) == 1
    assert len(characteristic_result.scalars().all()) == 1
