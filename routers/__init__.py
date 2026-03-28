from .auth.auth_router import auth_router
from .seller import seller_route

routes = [
    auth_router,
    seller_route.seller_router
]
