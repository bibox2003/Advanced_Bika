from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .api_views import (
    MeView,
    ProductListView,
    ProductDetailView,
    ProductStockAdjustView,
    CartListView,
    AddToCartView,
    UpdateCartItemView,
    RemoveCartItemView,
    CheckoutPreviewView,
    CheckoutCreateOrderView,
    session_to_jwt,
)

urlpatterns = [
    # Auth
    path("token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    # Session -> JWT bridge
    path("v1/session-to-jwt/", session_to_jwt, name="session_to_jwt"),

    # User
    path("v1/me/", MeView.as_view(), name="me"),

    # Products
    path("v1/products/", ProductListView.as_view(), name="products"),
    path("v1/products/<int:id>/", ProductDetailView.as_view(), name="product_detail"),
    path("v1/products/<int:id>/stock/", ProductStockAdjustView.as_view(), name="product_stock_adjust"),

    # Cart
    path("v1/cart/", CartListView.as_view(), name="cart_list"),
    path("v1/cart/add/", AddToCartView.as_view(), name="cart_add"),
    path("v1/cart/<int:item_id>/", UpdateCartItemView.as_view(), name="cart_update"),
    path("v1/cart/<int:item_id>/remove/", RemoveCartItemView.as_view(), name="cart_remove"),

    # Checkout
    path("v1/checkout/preview/", CheckoutPreviewView.as_view(), name="checkout_preview"),
    path("v1/checkout/create-order/", CheckoutCreateOrderView.as_view(), name="checkout_create_order"),
]
