from .auth.auth_router import auth_router
from .seller import seller_route
from .category import category_route
from .product import product_route
from .sku import sku_route
from .invoice import invoice_route
from .upload import upload_route
from .public import public_router

routes = [
    auth_router,
    seller_route.seller_router,
    category_route.category_router,
    product_route.product_router,
    sku_route.sku_router,
    invoice_route.invoice_router,
    upload_route.upload_router,
    public_router.public_router,
]
