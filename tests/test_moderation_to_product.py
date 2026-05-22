# TODO: переделать сервис модерации. Сейчас он типа не работает
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
from models.product import Product, ProductStatus
from models.seller import Seller
from models.sku import SKU
from models.outbox_event import OutboxEvent
from models.processed_event import ProcessedEvent

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
        await db_session.execute(delete(SKU))
        await db_session.execute(delete(Product).where(Product.seller_id == seller.id))
        await db_session.execute(delete(Category).where(Category.id == category.id))
        await db_session.execute(delete(Seller).where(Seller.id == seller.id))
        await db_session.commit()


@pytest.fixture
async def client_moderation(test_context, monkeypatch):
    monkeypatch.setattr(settings, "MOD_SERVICE_KEY", "test-mod-key")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def client_seller(test_context):
    async def _override_get_current_seller():
        return test_context["seller"]

    app.dependency_overrides[get_current_seller] = _override_get_current_seller
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(get_current_seller, None)


async def _create_product(db_session, test_context, status=ProductStatus.CREATED, **kwargs):
    product = Product(
        id=uuid4(),
        seller_id=test_context["seller"].id,
        category_id=test_context["category"].id,
        title=kwargs.get("title", "Test product"),
        slug=kwargs.get("slug", f"product-{uuid4()}"),
        description=kwargs.get("description", ""),
        status=status,
        deleted=False,
        blocked=False,
        blocking_reason_id=kwargs.get("blocking_reason_id"),
        moderator_comment=kwargs.get("moderator_comment"),
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    return product


async def test_moderated_event_clears_blocking_data(client_moderation, db_session, test_context):
    product = await _create_product(
        db_session,
        test_context,
        status=ProductStatus.BLOCKED,
        blocking_reason_id=uuid4(),
        moderator_comment="Было нарушение",
    )
    assert product.status == ProductStatus.BLOCKED
    assert product.blocking_reason_id is not None

    payload = {
        "idempotency_key": str(uuid4()),
        "event_type": "MODERATED",
        "product_id": str(product.id),
        "moderator_comment": "Одобрено",
    }
    response = await client_moderation.post(
        "/api/v1/events/product",
        json=payload,
        headers={"X-Service-Key": "test-mod-key"},
    )

    assert response.status_code == 200
    await db_session.refresh(product)
    assert product.status == ProductStatus.MODERATED
    assert product.blocking_reason_id is None
    assert product.moderator_comment == "Одобрено"
    processed = await db_session.execute(
        select(ProcessedEvent).where(
            ProcessedEvent.sender_service == "moderation",
            ProcessedEvent.idempotency_key == payload["idempotency_key"],
        )
    )
    assert processed.scalar_one_or_none() is not None


async def test_blocked_soft_saves_field_reports(client_moderation, db_session, test_context, monkeypatch):
    monkeypatch.setattr(settings, "B2C_SERVICE_URL", "http://b2c")
    product = await _create_product(db_session, test_context, status=ProductStatus.CREATED)
    blocking_reason_id = uuid4()

    payload = {
        "idempotency_key": str(uuid4()),
        "event_type": "BLOCKED",
        "product_id": str(product.id),
        "moderator_comment": "Нарушение правил",
        "blocking_reason_id": str(blocking_reason_id),
        "hard_block": False,
    }
    response = await client_moderation.post(
        "/api/v1/events/product",
        json=payload,
        headers={"X-Service-Key": "test-mod-key"},
    )

    assert response.status_code == 200
    await db_session.refresh(product)
    assert product.status == ProductStatus.BLOCKED
    assert product.blocked is True
    assert product.blocking_reason_id == blocking_reason_id
    assert product.moderator_comment == "Нарушение правил"

    outbox = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.event_type == "PRODUCT_BLOCKED")
    )
    events = outbox.scalars().all()
    assert len(events) == 1
    payload_out = json.loads(events[0].payload)
    assert payload_out["product_id"] == str(product.id)
    assert "sku_ids" in payload_out


async def test_blocked_hard_sets_terminal_status(
    client_moderation, db_session, test_context, monkeypatch
):
    monkeypatch.setattr(settings, "B2C_SERVICE_URL", "http://b2c")
    product = await _create_product(db_session, test_context, status=ProductStatus.CREATED)

    payload = {
        "idempotency_key": str(uuid4()),
        "event_type": "BLOCKED",
        "product_id": str(product.id),
        "moderator_comment": "Жёсткое нарушение",
        "blocking_reason_id": str(uuid4()),
        "hard_block": True,
    }
    response = await client_moderation.post(
        "/api/v1/events/product",
        json=payload,
        headers={"X-Service-Key": "test-mod-key"},
    )

    assert response.status_code == 200
    await db_session.refresh(product)
    assert product.status == ProductStatus.HARD_BLOCKED

    outbox = await db_session.execute(
        select(OutboxEvent).where(OutboxEvent.event_type == "PRODUCT_BLOCKED")
    )
    assert len(outbox.scalars().all()) == 1


async def test_hard_blocked_product_rejects_seller_edits(
    client_moderation, client_seller, db_session, test_context
):
    product = await _create_product(db_session, test_context, status=ProductStatus.CREATED)
    payload = {
        "idempotency_key": str(uuid4()),
        "event_type": "BLOCKED",
        "product_id": str(product.id),
        "moderator_comment": "Жёсткая блокировка",
        "blocking_reason_id": str(uuid4()),
        "hard_block": True,
    }
    await client_moderation.post(
        "/api/v1/events/product",
        json=payload,
        headers={"X-Service-Key": "test-mod-key"},
    )
    await db_session.refresh(product)
    assert product.status == ProductStatus.HARD_BLOCKED

    resp_patch = await client_seller.patch(
        f"/api/v1/products/{product.id}",
        json={"title": "Изменённый заголовок"},
    )
    assert resp_patch.status_code == 403

    resp_delete = await client_seller.delete(f"/api/v1/products/{product.id}")
    assert resp_delete.status_code == 403


async def test_duplicate_event_same_idempotency_key_no_side_effects(client_moderation, db_session, test_context):
    product = await _create_product(
        db_session,
        test_context,
        status=ProductStatus.BLOCKED,
        blocking_reason_id=uuid4(),
        moderator_comment="До повтора",
    )
    idem_key = str(uuid4())
    payload = {
        "idempotency_key": idem_key,
        "event_type": "MODERATED",
        "product_id": str(product.id),
        "moderator_comment": "После модерации",
    }
    resp1 = await client_moderation.post(
        "/api/v1/events/product",
        json=payload,
        headers={"X-Service-Key": "test-mod-key"},
    )
    assert resp1.status_code == 200
    await db_session.refresh(product)
    status_after_first = product.status
    comment_after_first = product.moderator_comment

    resp2 = await client_moderation.post(
        "/api/v1/events/product",
        json=payload,
        headers={"X-Service-Key": "test-mod-key"},
    )
    assert resp2.status_code == 200
    await db_session.refresh(product)
    assert product.status == status_after_first
    assert product.moderator_comment == comment_after_first
    count = await db_session.execute(
        select(ProcessedEvent).where(ProcessedEvent.idempotency_key == idem_key)
    )
    assert len(count.scalars().all()) == 1