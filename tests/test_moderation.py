import pytest
from uuid import uuid4, UUID
from datetime import datetime, timezone
import json
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from main import app
from core.database import AsyncSessionLocal, Base, engine
from core.config import settings
from core.security import create_access_token, hash_password
from models.product import Product, ProductStatus
from models.category import Category
from models.seller import Seller
from models.sku import SKU
from models.outbox_event import OutboxEvent
from models.processed_event import ProcessedEvent

pytestmark = pytest.mark.asyncio(loop_scope="session")


def make_moderation_payload(
    product_id: UUID, event_type: str,
    *, hard_block: bool = False,
    comment: str = "", id_key: str | None = None,
) -> dict:
    return {
        "idempotency_key": id_key or str(uuid4()),
        "product_id": str(product_id),
        "event_type": event_type,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "moderator_comment": comment,
        "hard_block": hard_block,
    }


@pytest.fixture(scope="session")
def moderation_headers():
    return {"X-Service-Key": settings.MOD_SERVICE_KEY}


@pytest.fixture(scope="session", autouse=True)
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture
async def db_session():
    async with AsyncSessionLocal() as session:
        yield session


@pytest.fixture(scope="session")
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def seller_token(db_session):
    seller_id = uuid4()
    seller = Seller(
        id=seller_id,
        email=f"seller_{uuid4().hex[:8]}@example.com",
        password_hash=hash_password("testpass123"),
        first_name="Test",
        last_name="Seller",
        company_name="Mod Test Seller",
        phone="+79990000000",
        inn=f"{uuid4().hex[:10]}",
    )
    db_session.add(seller)
    await db_session.commit()
    token = create_access_token(str(seller_id))
    yield token
    await db_session.execute(delete(Seller).where(Seller.id == seller_id))
    await db_session.commit()


@pytest.fixture
async def test_product(db_session, seller_token):
    import jwt
    payload = jwt.decode(seller_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    seller_id = UUID(payload["sub"])

    cat_id = uuid4()
    category = Category(id=cat_id, name="Test Category")
    db_session.add(category)
    await db_session.flush()

    product_id = uuid4()
    product = Product(
        id=product_id,
        seller_id=seller_id,
        title="Moderation Test Product",
        slug="moderation-test-product",
        description="Test description",
        status=ProductStatus.ON_MODERATION,
        category_id=cat_id,
    )
    db_session.add(product)

    sku = SKU(
        id=uuid4(),
        product_id=product_id,
        name="Test SKU",
        price=1000,
        active_quantity=10,
    )
    db_session.add(sku)
    await db_session.commit()

    yield product_id

    await db_session.execute(delete(SKU).where(SKU.product_id == product_id))
    await db_session.execute(delete(Product).where(Product.id == product_id))
    await db_session.execute(delete(Category).where(Category.id == cat_id))
    await db_session.commit()


# тесты
async def test_moderated_event_clears_blocking_data(
    client, moderation_headers, test_product, db_session
):
    async with db_session.begin():
        product = await db_session.get(Product, test_product)
        product.blocking_reason_id = uuid4()
        await db_session.commit()

    id_key = str(uuid4())
    resp = await client.post(
        "/api/v1/moderation/events",
        headers=moderation_headers,
        json=make_moderation_payload(test_product, "MODERATED", comment="Approved", id_key=id_key),
    )
    assert resp.status_code == 204

    async with db_session.begin():
        product = await db_session.get(Product, test_product)
        await db_session.refresh(product)
        assert product.status == ProductStatus.MODERATED
        assert product.blocking_reason_id is None
        assert product.moderator_comment == "Approved"


async def test_blocked_soft_saves_field_reports(
    client, moderation_headers, test_product, db_session
):
    resp = await client.post(
        "/api/v1/moderation/events",
        headers=moderation_headers,
        json=make_moderation_payload(test_product, "BLOCKED", comment="Needs improvement"),
    )
    assert resp.status_code == 204

    async with db_session.begin():
        product = await db_session.get(Product, test_product)
        await db_session.refresh(product)
        assert product.status == ProductStatus.BLOCKED
        assert product.moderator_comment == "Needs improvement"

    async with db_session.begin():
        result = await db_session.execute(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "PRODUCT_BLOCKED",
                OutboxEvent.target_url.like(f"%{settings.B2C_SERVICE_URL}%"),
                OutboxEvent.payload.like(f'%"product_id": "{test_product}"%')
            )
        )
        events = result.scalars().all()
        assert len(events) == 1
        payload = json.loads(events[0].payload)
        assert payload["product_id"] == str(test_product)


async def test_blocked_hard_sets_terminal_status(
    client, moderation_headers, test_product, db_session
):
    resp = await client.post(
        "/api/v1/moderation/events",
        headers=moderation_headers,
        json=make_moderation_payload(test_product, "BLOCKED", hard_block=True, comment="Permanent block"),
    )
    assert resp.status_code == 204

    async with db_session.begin():
        product = await db_session.get(Product, test_product)
        await db_session.refresh(product)
        assert product.status == ProductStatus.HARD_BLOCKED

    async with db_session.begin():
        result = await db_session.execute(
            select(OutboxEvent).where(
                OutboxEvent.event_type.in_(["PRODUCT_HARD_BLOCKED", "PRODUCT_BLOCKED"]),
                OutboxEvent.target_url.like(f"%{settings.B2C_SERVICE_URL}%"),
                OutboxEvent.payload.like(f'%"product_id": "{test_product}"%')
            )
        )
        events = result.scalars().all()
        assert len(events) >= 1
        payload = json.loads(events[0].payload)
        assert payload["product_id"] == str(test_product)


async def test_hard_blocked_product_rejects_seller_edits(
    client, moderation_headers, test_product, seller_token, db_session
):
    resp = await client.post(
        "/api/v1/moderation/events",
        headers=moderation_headers,
        json=make_moderation_payload(test_product, "BLOCKED", hard_block=True, comment="Terminal"),
    )
    assert resp.status_code == 204

    seller_headers = {"Authorization": f"Bearer {seller_token}"}

    update_resp = await client.patch(
        f"/api/v1/products/{test_product}",
        headers=seller_headers,
        json={"title": "New Title"},
    )
    assert update_resp.status_code == 403

    delete_resp = await client.delete(
        f"/api/v1/products/{test_product}",
        headers=seller_headers,
    )
    assert delete_resp.status_code == 403


async def test_duplicate_event_same_idempotency_key_no_side_effects(
    client, moderation_headers, test_product, db_session
):
    id_key = str(uuid4())
    payload = make_moderation_payload(test_product, "MODERATED", comment="First approval", id_key=id_key)

    resp1 = await client.post("/api/v1/moderation/events", headers=moderation_headers, json=payload)
    assert resp1.status_code == 204

    async with db_session.begin():
        product_before = await db_session.get(Product, test_product)
        await db_session.refresh(product_before)
        status_before = product_before.status
        comment_before = product_before.moderator_comment

    resp2 = await client.post("/api/v1/moderation/events", headers=moderation_headers, json=payload)
    assert resp2.status_code == 204

    async with db_session.begin():
        product_after = await db_session.get(Product, test_product)
        await db_session.refresh(product_after)
        assert product_after.status == status_before
        assert product_after.moderator_comment == comment_before

        result = await db_session.execute(
            select(ProcessedEvent).where(
                ProcessedEvent.sender_service == "moderation",
                ProcessedEvent.idempotency_key == id_key,
            )
        )
        events = result.scalars().all()
        assert len(events) == 1