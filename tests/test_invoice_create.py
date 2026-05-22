import asyncio
import pytest
from uuid import uuid4
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete
from core.database import AsyncSessionLocal, Base, engine
from core.dependencies import get_current_seller
from main import app
from models.category import Category
from models.invoice import Invoice, InvoiceStatus
from models.invoice_item import InvoiceItem
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
        await db_session.execute(delete(InvoiceItem))
        await db_session.execute(delete(Invoice))
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


@pytest.fixture
async def moderated_product(db_session, test_context) -> Product:
    product = Product(
        id=uuid4(),
        seller_id=test_context["seller"].id,
        category_id=test_context["category"].id,
        title="Moderated product",
        slug=f"moderated-product-{uuid4()}",
        description="",
        status=ProductStatus.MODERATED,
        deleted=False,
        blocked=False,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    return product


@pytest.fixture
async def moderated_sku(db_session, moderated_product) -> SKU:
    sku = SKU(
        id=uuid4(),
        product_id=moderated_product.id,
        name="Moderated SKU",
        price=1000,
        discount=0,
        cost_price=500,
        active_quantity=0,
        reserved_quantity=0,
        article=None,
    )
    db_session.add(sku)
    await db_session.commit()
    await db_session.refresh(sku)
    return sku


async def test_create_invoice_with_moderated_sku_returns_201(client, moderated_sku):
    payload = {
        "items": [
            {
                "sku_id": str(moderated_sku.id),
                "quantity": 2,
            }
        ]
    }

    response = await client.post("/api/v1/invoices", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["status"] == InvoiceStatus.CREATED.value


async def test_empty_items_returns_400(client):
    response = await client.post("/api/v1/invoices", json={"items": []})

    assert response.status_code == 400


async def test_non_moderated_sku_returns_400(client, db_session, test_context):
    product = Product(
        id=uuid4(),
        seller_id=test_context["seller"].id,
        category_id=test_context["category"].id,
        title="Not moderated",
        slug=f"not-moderated-{uuid4()}",
        description="",
        status=ProductStatus.CREATED,
        deleted=False,
        blocked=False,
    )
    db_session.add(product)
    await db_session.commit()

    sku = SKU(
        id=uuid4(),
        product_id=product.id,
        name="SKU",
        price=1000,
        discount=0,
        cost_price=500,
        active_quantity=0,
        reserved_quantity=0,
        article=None,
    )
    db_session.add(sku)
    await db_session.commit()

    response = await client.post(
        "/api/v1/invoices",
        json={"items": [{"sku_id": str(sku.id), "quantity": 1}]},
    )

    assert response.status_code == 400


async def test_others_sku_returns_403(client, db_session, test_context):
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

    product = Product(
        id=uuid4(),
        seller_id=other_seller.id,
        category_id=test_context["category"].id,
        title="Other product",
        slug=f"other-product-{uuid4()}",
        description="",
        status=ProductStatus.MODERATED,
        deleted=False,
        blocked=False,
    )
    db_session.add(product)
    await db_session.commit()

    sku = SKU(
        id=uuid4(),
        product_id=product.id,
        name="Other SKU",
        price=1000,
        discount=0,
        cost_price=500,
        active_quantity=0,
        reserved_quantity=0,
        article=None,
    )
    db_session.add(sku)
    await db_session.commit()

    response = await client.post(
        "/api/v1/invoices",
        json={"items": [{"sku_id": str(sku.id), "quantity": 1}]},
    )

    assert response.status_code == 403

    await db_session.execute(delete(Product).where(Product.id == product.id))
    await db_session.execute(delete(Seller).where(Seller.id == other_seller.id))
    await db_session.commit()


async def test_accept_invoice_full(client, db_session, moderated_sku):
    payload = {"items": [{"sku_id": str(moderated_sku.id), "quantity": 5}]}
    resp = await client.post("/api/v1/invoices", json=payload)
    assert resp.status_code == 201
    invoice = resp.json()
    
    resp_accept = await client.post(f"/api/v1/invoices/{invoice['id']}/accept")
    assert resp_accept.status_code == 200
    data = resp_accept.json()
    assert data["status"] == "ACCEPTED"
    assert data["accepted_at"] is not None
    assert data["accepted_by"] is not None
    assert len(data["items"]) == 1
    assert data["items"][0]["accepted_quantity"] == 5
    await db_session.refresh(moderated_sku)
    assert moderated_sku.active_quantity == 5


async def test_accept_invoice_partial(client, db_session, test_context, moderated_product, moderated_sku):
    sku2 = SKU(
        id=uuid4(),
        product_id=moderated_product.id,
        name="SKU2",
        price=100,
        discount=0,
        cost_price=50,
        active_quantity=0,
        reserved_quantity=0
    )
    db_session.add(sku2)
    await db_session.commit()
    
    payload = {
        "items": [
            {"sku_id": str(moderated_sku.id), "quantity": 10},
            {"sku_id": str(sku2.id), "quantity": 5}
        ]
    }
    resp = await client.post("/api/v1/invoices", json=payload)
    assert resp.status_code == 201
    invoice = resp.json()
    
    accept_payload = {
        "accepted_items": [
            {"invoice_item_id": invoice["items"][0]["id"], "accepted_quantity": 10},
            {"invoice_item_id": invoice["items"][1]["id"], "accepted_quantity": 2}
        ]
    }
    resp_accept = await client.post(
        f"/api/v1/invoices/{invoice['id']}/accept",
        json=accept_payload
    )
    assert resp_accept.status_code == 200
    data = resp_accept.json()
    assert data["status"] == "PARTIALLY_ACCEPTED"
    assert data["items"][0]["accepted_quantity"] == 10
    assert data["items"][1]["accepted_quantity"] == 2
    
    await db_session.refresh(moderated_sku)
    await db_session.refresh(sku2)
    assert moderated_sku.active_quantity == 10
    assert sku2.active_quantity == 2


async def test_accept_already_accepted_fails(client, moderated_sku):
    payload = {"items": [{"sku_id": str(moderated_sku.id), "quantity": 1}]}
    resp = await client.post("/api/v1/invoices", json=payload)
    assert resp.status_code == 201
    invoice = resp.json()
    
    await client.post(f"/api/v1/invoices/{invoice['id']}/accept")
    resp2 = await client.post(f"/api/v1/invoices/{invoice['id']}/accept")
    assert resp2.status_code == 400


async def test_accept_exceeding_quantity_fails(client, moderated_sku):
    payload = {"items": [{"sku_id": str(moderated_sku.id), "quantity": 5}]}
    resp = await client.post("/api/v1/invoices", json=payload)
    assert resp.status_code == 201
    invoice = resp.json()
    
    resp_accept = await client.post(
        f"/api/v1/invoices/{invoice['id']}/accept",
        json={
            "accepted_items": [
                {"invoice_item_id": invoice["items"][0]["id"], "accepted_quantity": 10}
            ]
        }
    )
    assert resp_accept.status_code == 400