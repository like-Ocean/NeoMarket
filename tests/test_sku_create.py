import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, Mock, patch
from fastapi import HTTPException

from core.config import settings
from models.product import Product, ProductStatus
from models.sku_image import SKUImage
from models.sku_characteristic import SKUCharacteristic
from models.seller import Seller
from schemas.sku import SKUCreate
from services import sku_service


class _ScalarResult:
    def __init__(self, scalar_value=None, scalar_one_value=None):
        self._scalar_value = scalar_value
        self._scalar_one_value = scalar_one_value

    def scalar_one_or_none(self):
        return self._scalar_value

    def scalar_one(self):
        return self._scalar_one_value


def _build_seller() -> Seller:
    return Seller(
        id=uuid4(),
        email="seller@example.com",
        password_hash="fake",
        first_name="Test",
        last_name="Seller",
        company_name="Test Company",
        inn="1111111111",
    )


def _build_product(seller_id, status: ProductStatus) -> Product:
    return Product(
        id=uuid4(),
        seller_id=seller_id,
        category_id=uuid4(),
        title="Test product",
        slug="test-product",
        description="",
        status=status,
        deleted=False,
        blocked=False,
    )


def _build_sku_payload(
    product_id,
    article: str | None = None,
    images: list[dict] | None = None,
    characteristics: list[dict] | None = None,
) -> SKUCreate:
    return SKUCreate(
        product_id=product_id,
        name="SKU A",
        price=1000,
        discount=0,
        cost_price=None,
        article=article,
        images=images or [],
        characteristics=characteristics or [],
    )


@pytest.mark.asyncio
async def test_add_sku_product_not_found_returns_404():
    seller = _build_seller()
    payload = _build_sku_payload(uuid4())

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_ScalarResult(scalar_value=None)])

    with pytest.raises(HTTPException) as exc_info:
        await sku_service.create_sku(db, seller, payload)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_add_sku_wrong_seller_returns_404():
    seller = _build_seller()
    product = _build_product(uuid4(), ProductStatus.CREATED)
    payload = _build_sku_payload(product.id)

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_ScalarResult(scalar_value=product)])

    with pytest.raises(HTTPException) as exc_info:
        await sku_service.create_sku(db, seller, payload)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_add_sku_to_on_moderation_returns_403():
    seller = _build_seller()
    product = _build_product(seller.id, ProductStatus.ON_MODERATION)
    payload = _build_sku_payload(product.id)

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_ScalarResult(scalar_value=product)])

    with pytest.raises(HTTPException) as exc_info:
        await sku_service.create_sku(db, seller, payload)

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_add_sku_with_duplicate_article_returns_409():
    seller = _build_seller()
    product = _build_product(seller.id, ProductStatus.CREATED)
    payload = _build_sku_payload(product.id, article="ART-1")

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _ScalarResult(scalar_value=product),
        _ScalarResult(scalar_value=object()),
    ])

    with pytest.raises(HTTPException) as exc_info:
        await sku_service.create_sku(db, seller, payload)

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_add_sku_creates_images_and_characteristics():
    seller = _build_seller()
    product = _build_product(seller.id, ProductStatus.CREATED)
    payload = _build_sku_payload(
        product.id,
        images=[{"url": "http://img/1.jpg", "ordering": 1}],
        characteristics=[{"name": "Color", "value": "Black"}],
    )

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _ScalarResult(scalar_value=product),
        _ScalarResult(scalar_one_value=1),
    ])
    db.add = Mock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    with patch("services.sku_service.get_sku_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = AsyncMock()
        await sku_service.create_sku(db, seller, payload)

    added_types = [type(call.args[0]) for call in db.add.call_args_list]
    assert SKUImage in added_types
    assert SKUCharacteristic in added_types


@pytest.mark.asyncio
async def test_first_sku_transitions_product_to_on_moderation(monkeypatch):
    seller = _build_seller()
    product = _build_product(seller.id, ProductStatus.CREATED)
    payload = _build_sku_payload(product.id)

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _ScalarResult(scalar_value=product),
        _ScalarResult(scalar_one_value=0),
    ])
    db.add = Mock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    # Только базовый URL
    monkeypatch.setattr(
        settings,
        "MODERATION_SERVICE_URL",
        "http://moderation",  # Убрали /api/v1/events/product
    )

    with patch("services.sku_service.add_outbox_event", new_callable=AsyncMock), \
        patch("services.sku_service.get_sku_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = AsyncMock()
        await sku_service.create_sku(db, seller, payload)

    assert product.status == ProductStatus.ON_MODERATION


@pytest.mark.asyncio
async def test_first_sku_emits_created_event_to_moderation(monkeypatch):
    seller = _build_seller()
    product = _build_product(seller.id, ProductStatus.CREATED)
    payload = _build_sku_payload(product.id)

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _ScalarResult(scalar_value=product),
        _ScalarResult(scalar_one_value=0),
    ])
    db.add = Mock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    moderation_url = "http://moderation"
    monkeypatch.setattr(sku_service.settings, "MODERATION_SERVICE_URL", moderation_url)

    expected_url = f"{moderation_url}/api/v1/events/product"

    with patch("services.sku_service.add_outbox_event", new_callable=AsyncMock) as mock_outbox, \
        patch("services.sku_service.get_sku_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = AsyncMock()
        await sku_service.create_sku(db, seller, payload)

    mock_outbox.assert_awaited_once()
    args, kwargs = mock_outbox.await_args
    assert kwargs["event_type"] == "CREATED"
    assert kwargs["target_url"] == expected_url
    assert kwargs["payload"]["product_id"] == str(product.id)
    assert kwargs["payload"]["seller_id"] == str(seller.id)
    assert kwargs["payload"]["event"] == "CREATED"
    assert "date" in kwargs["payload"]


@pytest.mark.asyncio
async def test_second_sku_no_state_change(monkeypatch):
    seller = _build_seller()
    product = _build_product(seller.id, ProductStatus.CREATED)
    payload = _build_sku_payload(product.id)

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[
        _ScalarResult(scalar_value=product),
        _ScalarResult(scalar_one_value=1),
    ])
    db.add = Mock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    monkeypatch.setattr(
        settings,
        "MODERATION_SERVICE_URL",
        "http://moderation/api/v1/events/product",
    )

    with patch("services.sku_service.add_outbox_event", new_callable=AsyncMock) as mock_outbox, \
        patch("services.sku_service.get_sku_by_id", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = AsyncMock()
        await sku_service.create_sku(db, seller, payload)

    assert product.status == ProductStatus.CREATED
    mock_outbox.assert_not_called()


@pytest.mark.asyncio
async def test_add_sku_to_hard_blocked_returns_403(monkeypatch):
    seller = _build_seller()
    product = _build_product(seller.id, ProductStatus.HARD_BLOCKED)
    payload = _build_sku_payload(product.id)

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_ScalarResult(scalar_value=product)])

    with patch("services.sku_service.add_outbox_event", new_callable=AsyncMock) as mock_outbox, \
        patch("services.sku_service.get_sku_by_id", new_callable=AsyncMock):
        with pytest.raises(HTTPException) as exc_info:
            await sku_service.create_sku(db, seller, payload)

    assert exc_info.value.status_code == 403
    mock_outbox.assert_not_called()
