import asyncio
import pytest
from uuid import uuid4
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete
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


async def _create_product(
    db_session,
    seller_id,
    category_id,
    status: ProductStatus = ProductStatus.CREATED,
    title: str = "Product",
    deleted: bool = False,
) -> Product:
    product = Product(
        id=uuid4(),
        seller_id=seller_id,
        category_id=category_id,
        title=title,
        slug=f"product-{uuid4()}",
        description="",
        status=status,
        deleted=deleted,
        blocked=False,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)
    return product


async def test_list_returns_only_own_products(client, db_session, test_context):
    own_product = await _create_product(
        db_session,
        seller_id=test_context["seller"].id,
        category_id=test_context["category"].id,
        title="Own",
    )
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

    other_product = await _create_product(
        db_session,
        seller_id=other_seller.id,
        category_id=test_context["category"].id,
        title="Other",
    )

    response = await client.get("/api/v1/products")

    assert response.status_code == 200
    items = response.json()["items"]
    item_ids = {item["id"] for item in items}
    assert str(own_product.id) in item_ids
    assert str(other_product.id) not in item_ids

    await db_session.execute(delete(Product).where(Product.id == other_product.id))
    await db_session.execute(delete(Seller).where(Seller.id == other_seller.id))
    await db_session.commit()


async def test_idor_query_param_seller_id_ignored(client, db_session, test_context):
    own_product = await _create_product(
        db_session,
        seller_id=test_context["seller"].id,
        category_id=test_context["category"].id,
        title="Own",
    )
    other_seller = Seller(
        id=uuid4(),
        email=f"other-idor-{uuid4()}@example.com",
        password_hash="fake_hash",
        first_name="Other",
        last_name="Seller",
        company_name="Other Company",
        inn=str(uuid4()).replace("-", "")[:12],
    )
    db_session.add(other_seller)
    await db_session.commit()

    other_product = await _create_product(
        db_session,
        seller_id=other_seller.id,
        category_id=test_context["category"].id,
        title="Other",
    )

    response = await client.get(
        "/api/v1/products",
        params={"seller_id": str(other_seller.id)},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    item_ids = {item["id"] for item in items}
    assert str(own_product.id) in item_ids
    assert str(other_product.id) not in item_ids

    await db_session.execute(delete(Product).where(Product.id == other_product.id))
    await db_session.execute(delete(Seller).where(Seller.id == other_seller.id))
    await db_session.commit()


async def test_deleted_products_visible_with_deleted_flag(client, db_session, test_context):
    deleted_product = await _create_product(
        db_session,
        seller_id=test_context["seller"].id,
        category_id=test_context["category"].id,
        title="Deleted",
        deleted=True,
    )

    response = await client.get(
        "/api/v1/products",
        params={"include_deleted": "true"},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    deleted_items = [item for item in items if item["id"] == str(deleted_product.id)]
    assert len(deleted_items) == 1
    assert deleted_items[0]["deleted"] is True


async def test_status_filter_works_correctly(client, db_session, test_context):
    blocked_product = await _create_product(
        db_session,
        seller_id=test_context["seller"].id,
        category_id=test_context["category"].id,
        status=ProductStatus.BLOCKED,
        title="Blocked",
    )
    await _create_product(
        db_session,
        seller_id=test_context["seller"].id,
        category_id=test_context["category"].id,
        status=ProductStatus.CREATED,
        title="Created",
    )

    response = await client.get(
        "/api/v1/products",
        params={"status": "BLOCKED"},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) >= 1
    item_ids = {item["id"] for item in items}
    assert str(blocked_product.id) in item_ids
    assert all(item["status"] == ProductStatus.BLOCKED.value for item in items)


async def test_search_by_title_case_insensitive(client, db_session, test_context):
    target = await _create_product(
        db_session,
        seller_id=test_context["seller"].id,
        category_id=test_context["category"].id,
        title="Super Phone",
    )
    await _create_product(
        db_session,
        seller_id=test_context["seller"].id,
        category_id=test_context["category"].id,
        title="Other",
    )

    response = await client.get(
        "/api/v1/products",
        params={"search": "super"},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    item_ids = {item["id"] for item in items}
    assert str(target.id) in item_ids
