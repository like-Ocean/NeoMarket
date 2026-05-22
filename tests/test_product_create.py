import asyncio
import json
import pytest
from uuid import UUID, uuid4
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete, select
from core.database import AsyncSessionLocal, Base, engine
from core.dependencies import get_current_seller
from main import app
from models.category import Category
from models.product import Product, ProductStatus
from models.seller import Seller
from models.invoice_item import InvoiceItem
from core.config import settings
from models.outbox_event import OutboxEvent
from core.dependencies import get_current_seller, get_current_seller_optional
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

    async def _override():
        return seller
    
    app.dependency_overrides[get_current_seller] = _override
    app.dependency_overrides[get_current_seller_optional] = _override

    try:
        yield {"seller": seller, "category": category}
    finally:
        app.dependency_overrides.pop(get_current_seller, None)
        app.dependency_overrides.pop(get_current_seller_optional, None)
        await db_session.execute(delete(OutboxEvent))
        await db_session.execute(delete(InvoiceItem))
        await db_session.execute(delete(SKU).where(
            SKU.product_id.in_(select(Product.id).where(Product.seller_id == seller.id))
        ))
        await db_session.execute(delete(Product).where(Product.seller_id == seller.id))
        await db_session.execute(delete(Category).where(Category.id == category.id))
        await db_session.execute(delete(Seller).where(Seller.id == seller.id))
        await db_session.commit()


@pytest.fixture
async def client(test_context):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def valid_product_payload(test_context):
    return {
        "category_id": str(test_context["category"].id),
        "title": "Ноутбук Acer",
        "slug": f"test-slug-{uuid4()}",
        "description": "Отличный ноутбук для работы",
        "images": [
            {"url": "https://example.com/img1.jpg", "ordering": 0},
            {"url": "https://example.com/img2.jpg", "ordering": 1},
        ],
        "characteristics": [
            {"name": "Процессор", "value": "Intel i7"},
            {"name": "ОЗУ", "value": "16 GB"},
        ],
    }


@pytest.fixture
async def product_factory(db_session, test_context):
    async def _factory(
        status: ProductStatus = ProductStatus.CREATED,
        blocking_reason_id=None,
        moderator_comment=None
    ) -> Product:
        product = Product(
            id=uuid4(),
            seller_id=test_context["seller"].id,
            category_id=test_context["category"].id,
            title="Test product",
            slug=f"test-product-{uuid4()}",
            description="",
            status=status,
            blocking_reason_id=blocking_reason_id,
            moderator_comment=moderator_comment,
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


async def test_create_product_returns_201_with_created_status(
    client, valid_product_payload, test_context
):
    response = await client.post("/api/v1/products", json=valid_product_payload)

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == ProductStatus.CREATED.value
    assert data["skus"] == []
    assert data["seller_id"] == str(test_context["seller"].id)


async def test_seller_id_taken_from_jwt(
    client, valid_product_payload, test_context, db_session
):
    payload_with_seller = valid_product_payload.copy()
    payload_with_seller["seller_id"] = str(uuid4())

    response = await client.post("/api/v1/products", json=payload_with_seller)

    assert response.status_code == 201
    data = response.json()
    assert data["seller_id"] == str(test_context["seller"].id)

    result = await db_session.execute(
        select(Product).where(Product.id == UUID(data["id"]))
    )
    product = result.scalar_one()
    assert product.seller_id == test_context["seller"].id


async def test_missing_images_returns_400(client, valid_product_payload):
    payload = valid_product_payload.copy()
    payload.pop("images")

    response = await client.post("/api/v1/products", json=payload)

    assert response.status_code == 400
    data = response.json()
    assert data["message"] == "At least one image is required"


async def test_missing_category_returns_400(client, valid_product_payload):
    payload = valid_product_payload.copy()
    payload["category_id"] = str(uuid4())

    response = await client.post("/api/v1/products", json=payload)

    assert response.status_code == 400
    data = response.json()
    assert data["message"] == "Category not found"


async def test_missing_category_id_returns_422(client, valid_product_payload):
    payload = valid_product_payload.copy()
    payload.pop("category_id")

    response = await client.post("/api/v1/products", json=payload)

    assert response.status_code == 422
    data = response.json()
    assert data["code"] == "VALIDATION_ERROR"
    assert "message" in data
    assert "details" in data
    assert any(
        error["loc"][-1] == "category_id"
        for error in data["details"]
    )


async def test_empty_title_returns_400(client, valid_product_payload):
    payload = valid_product_payload.copy()
    payload["title"] = " "

    response = await client.post("/api/v1/products", json=payload)

    assert response.status_code == 400
    data = response.json()
    assert data["message"] == "title is required"


async def test_title_too_long_returns_400(client, valid_product_payload):
    payload = valid_product_payload.copy()
    payload["title"] = "a" * 256

    response = await client.post("/api/v1/products", json=payload)

    assert response.status_code == 400
    data = response.json()
    assert data["message"] == "title must be 1-255 characters"


async def test_invalid_category_uuid_returns_422(client, valid_product_payload):
    payload = valid_product_payload.copy()
    payload["category_id"] = "not-a-uuid"

    response = await client.post("/api/v1/products", json=payload)

    assert response.status_code == 422
    data = response.json()
    assert data["code"] == "VALIDATION_ERROR"
    assert "message" in data
    assert "details" in data
    assert any(
        error["loc"][-1] == "category_id"
        for error in data["details"]
    )


async def test_delete_sets_deleted_true(client, product, db_session):
    response = await client.delete(f"/api/v1/products/{product.id}")

    assert response.status_code == 204
    await db_session.refresh(product)
    assert product.deleted is True


async def test_delete_emits_event_to_moderation(client, product, db_session, monkeypatch):
    monkeypatch.setattr(settings, "MODERATION_SERVICE_URL", "http://moderation")
    await db_session.execute(delete(OutboxEvent))
    await db_session.commit()

    response = await client.delete(f"/api/v1/products/{product.id}")

    assert response.status_code == 204
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


async def test_delete_emits_product_deleted_to_b2c(client, product, db_session, monkeypatch):
    monkeypatch.setattr(settings, "B2C_SERVICE_URL", "http://b2c")
    await db_session.execute(delete(OutboxEvent))
    await db_session.commit()

    sku1 = SKU(
        id=uuid4(),
        product_id=product.id,
        name="SKU 1",
        price=1000,
        discount=0,
        cost_price=None,
        active_quantity=0,
        reserved_quantity=0,
        article=None,
    )
    sku2 = SKU(
        id=uuid4(),
        product_id=product.id,
        name="SKU 2",
        price=1100,
        discount=0,
        cost_price=None,
        active_quantity=0,
        reserved_quantity=0,
        article=None,
    )
    db_session.add_all([sku1, sku2])
    await db_session.commit()

    response = await client.delete(f"/api/v1/products/{product.id}")

    assert response.status_code == 204
    result = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.event_type == "PRODUCT_DELETED")
    )
    events = result.scalars().all()
    assert len(events) == 1

    event = events[0]
    assert event.target_url == "http://b2c"

    payload = json.loads(event.payload)
    assert payload["product_id"] == str(product.id)
    assert sorted(payload["sku_ids"]) == sorted([str(sku1.id), str(sku2.id)])
    assert payload["event"] == "PRODUCT_DELETED"
    assert "date" in payload


async def test_delete_already_deleted_returns_400(client, product, db_session):
    response = await client.delete(f"/api/v1/products/{product.id}")
    assert response.status_code == 204

    response = await client.delete(f"/api/v1/products/{product.id}")
    assert response.status_code == 400


async def test_deleted_product_not_in_seller_list(client, product_factory, db_session):
    deleted_product = await product_factory(status=ProductStatus.CREATED)
    active_product = await product_factory(status=ProductStatus.CREATED)

    response = await client.delete(f"/api/v1/products/{deleted_product.id}")
    assert response.status_code == 204

    response = await client.get("/api/v1/products")
    assert response.status_code == 200

    items = response.json()["items"]
    item_ids = {item["id"] for item in items}
    assert str(deleted_product.id) not in item_ids
    assert str(active_product.id) in item_ids


# ──────────────────────────────────────────────
# Тест 1: MODERATED — полный payload с SKU и cost_price, blocking_reason=null
# ──────────────────────────────────────────────

@pytest.fixture
async def sku_factory(db_session, test_context):
    async def _factory(product: Product, cost_price: int | None = 500) -> SKU:
        sku = SKU(
            id=uuid4(),
            product_id=product.id,
            name=f"SKU-{uuid4()}",
            price=1000,
            discount=0,
            cost_price=cost_price,
            active_quantity=5,
            reserved_quantity=0,
            article=None,
        )
        db_session.add(sku)
        await db_session.commit()
        await db_session.refresh(sku)
        return sku

    return _factory


async def test_get_moderated_product_returns_full_payload(
    client, test_context, product_factory, sku_factory
):
    product = await product_factory(
        status=ProductStatus.MODERATED,
        blocking_reason_id=None,
        moderator_comment=None,
    )
    sku = await sku_factory(product, cost_price=750)

    response = await client.get(f"/api/v1/products/{product.id}")

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == str(product.id)
    assert data["seller_id"] == str(product.seller_id)
    assert data["category_id"] == str(product.category_id)
    assert data["title"] == product.title
    assert data["description"] == product.description
    assert data["status"] == ProductStatus.MODERATED.value
    assert data["deleted"] is False
    assert data["blocking_reason_id"] is None

    assert len(data["skus"]) == 1
    sku_data = data["skus"][0]
    assert sku_data["id"] == str(sku.id)
    assert sku_data["cost_price"] == 750
    assert sku_data["price"] == 1000


# ──────────────────────────────────────────────
# Тест 2: BLOCKED — blocking_reason_id и moderator_comment в ответе
# ──────────────────────────────────────────────

async def test_get_blocked_product_returns_blocking_reason_and_field_reports(
    client, test_context, product_factory
):
    blocking_reason_id = uuid4()
    moderator_comment = "Нарушение правил: запрещённый товар"

    product = await product_factory(
        status=ProductStatus.BLOCKED,
        blocking_reason_id=blocking_reason_id,
        moderator_comment=moderator_comment,
    )

    response = await client.get(f"/api/v1/products/{product.id}")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == ProductStatus.BLOCKED.value
    assert data["blocking_reason_id"] == str(blocking_reason_id)
    assert data["moderator_comment"] == moderator_comment


# ──────────────────────────────────────────────
# Тест 3: чужой товар → 404 (не 403)
# ──────────────────────────────────────────────

async def test_get_others_product_returns_404(client, db_session, test_context):
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

    other_product = Product(
        id=uuid4(),
        seller_id=other_seller.id,
        category_id=test_context["category"].id,
        title="Other seller product",
        slug=f"other-product-{uuid4()}",
        description="Not yours",
        status=ProductStatus.CREATED,
        deleted=False,
        blocked=False,
    )
    db_session.add(other_product)
    await db_session.commit()

    try:
        response = await client.get(f"/api/v1/products/{other_product.id}")
        assert response.status_code == 404
    finally:
        await db_session.execute(delete(Product).where(Product.id == other_product.id))
        await db_session.execute(delete(Seller).where(Seller.id == other_seller.id))
        await db_session.commit()


# ──────────────────────────────────────────────
# Тест 4: несуществующий ID → 404
# ──────────────────────────────────────────────

async def test_get_nonexistent_returns_404(client, test_context):
    response = await client.get(f"/api/v1/products/{uuid4()}")

    assert response.status_code == 404