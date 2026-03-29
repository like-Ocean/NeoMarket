from .auth.auth_router import auth_router
from .seller import seller_route
from .category import category_route
from .product import product_route

routes = [
    auth_router,
    seller_route.seller_router,
    category_route.category_router,
    product_route.product_router,
]
