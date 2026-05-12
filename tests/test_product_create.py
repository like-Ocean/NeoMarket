import asyncio
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


async def test_create_product_returns_201_with_created_status(
    client, valid_product_payload, test_context
):
    response = await client.post("/api/products", json=valid_product_payload)

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

    response = await client.post("/api/products", json=payload_with_seller)

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

    response = await client.post("/api/products", json=payload)

    assert response.status_code == 400
    data = response.json()
    assert data["message"] == "At least one image is required"


async def test_missing_category_returns_400(client, valid_product_payload):
    payload = valid_product_payload.copy()
    payload["category_id"] = str(uuid4())

    response = await client.post("/api/products", json=payload)

    assert response.status_code == 400
    data = response.json()
    assert data["message"] == "Category not found"


async def test_missing_category_id_returns_422(client, valid_product_payload):
    payload = valid_product_payload.copy()
    payload.pop("category_id")

    response = await client.post("/api/products", json=payload)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(item["loc"][-1] == "category_id" for item in detail)


async def test_empty_title_returns_400(client, valid_product_payload):
    payload = valid_product_payload.copy()
    payload["title"] = " "

    response = await client.post("/api/products", json=payload)

    assert response.status_code == 400
    data = response.json()
    assert data["message"] == "title is required"


async def test_title_too_long_returns_400(client, valid_product_payload):
    payload = valid_product_payload.copy()
    payload["title"] = "a" * 256

    response = await client.post("/api/products", json=payload)

    assert response.status_code == 400
    data = response.json()
    assert data["message"] == "title must be 1-255 characters"


async def test_invalid_category_uuid_returns_422(client, valid_product_payload):
    payload = valid_product_payload.copy()
    payload["category_id"] = "not-a-uuid"

    response = await client.post("/api/products", json=payload)

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(item["loc"][-1] == "category_id" for item in detail)