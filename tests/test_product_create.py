import pytest
from uuid import uuid4
from datetime import datetime
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport
from main import app
from core.database import get_db
from core.dependencies import get_current_seller
from models.seller import Seller
from models.product import ProductStatus
from schemas.product import ProductResponse


TEST_SELLER_ID = uuid4()
TEST_SELLER = Seller(
    id=TEST_SELLER_ID,
    email="test@example.com",
    password_hash="fake_hash",
    first_name="Test",
    last_name="Seller",
    company_name="Test Company",
    inn="1111111111",
)


async def override_get_db():
    mock_session = AsyncMock()
    yield mock_session


async def override_get_current_seller():
    return TEST_SELLER


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_current_seller] = override_get_current_seller


@pytest.fixture
async def client():
    """Async клиент с ASGITransport для тестирования FastAPI."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def valid_product_payload():
    """Базовый валидный payload для создания товара."""
    return {
        "category_id": str(uuid4()),
        "title": "Ноутбук Acer",
        "slug": "test-slug",
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


@pytest.mark.asyncio
async def test_create_product_returns_201_with_created_status(client, valid_product_payload):
    with patch("services.product_service.create_product", new_callable=AsyncMock) as mock_create:
        product_id = uuid4()
        expected_response = ProductResponse(
            id=product_id,
            seller_id=TEST_SELLER_ID,
            category_id=uuid4(),
            title=valid_product_payload["title"],
            description=valid_product_payload["description"],
            slug=valid_product_payload["slug"],
            deleted=False,
            blocked=False,
            blocking_reason_id=None,
            moderator_comment=None,
            status=ProductStatus.CREATED,
            images=[],
            characteristics=[],
            skus=[],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        mock_create.return_value = expected_response

        response = await client.post("/api/products", json=valid_product_payload)

        assert response.status_code == 201
        data = response.json()
        assert data["status"] == ProductStatus.CREATED.value
        assert data["skus"] == []
        assert data["id"] == str(product_id)


@pytest.mark.asyncio
async def test_seller_id_taken_from_jwt(client, valid_product_payload):
    payload_with_seller = valid_product_payload.copy()
    payload_with_seller["seller_id"] = str(uuid4())

    with patch("services.product_service.create_product", new_callable=AsyncMock) as mock_create:
        product_id = uuid4()
        expected_response = ProductResponse(
            id=product_id,
            seller_id=TEST_SELLER_ID,
            category_id=uuid4(),
            title=valid_product_payload["title"],
            description=valid_product_payload["description"],
            slug=valid_product_payload["slug"],
            deleted=False,
            blocked=False,
            blocking_reason_id=None,
            moderator_comment=None,
            status=ProductStatus.CREATED,
            images=[],
            characteristics=[],
            skus=[],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        mock_create.return_value = expected_response

        response = await client.post("/api/products", json=payload_with_seller)

        assert response.status_code == 201
        data = response.json()
        assert data["seller_id"] == str(TEST_SELLER_ID)

        called_seller = mock_create.call_args[0][1]
        assert called_seller.id == TEST_SELLER_ID


@pytest.mark.asyncio
async def test_missing_images_returns_400(client, valid_product_payload):
    payload = valid_product_payload.copy()
    payload.pop("images")
    with patch("services.product_service.create_product", new_callable=AsyncMock) as mock_create:
        product_id = uuid4()
        expected_response = ProductResponse(
            id=product_id,
            seller_id=TEST_SELLER_ID,
            category_id=uuid4(),
            title=valid_product_payload["title"],
            description=valid_product_payload["description"],
            slug=valid_product_payload["slug"],
            deleted=False,
            blocked=False,
            blocking_reason_id=None,
            moderator_comment=None,
            status=ProductStatus.CREATED,
            images=[],
            characteristics=[],
            skus=[],
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        mock_create.return_value = expected_response

        response = await client.post("/api/products", json=payload)
        assert response.status_code == 201


@pytest.mark.asyncio
async def test_missing_category_returns_400(client, valid_product_payload):
    payload = valid_product_payload.copy()
    payload.pop("category_id")

    response = await client.post("/api/products", json=payload)
    assert response.status_code == 422