# bika/api_urls.py
from django.urls import path
from .api_views import (
    MeView,
    DashboardSummaryView,
    ProductListView,
    ProductDetailView,
    ProductCreateView,
    ProductUpdateView,
    ProductDeleteView,
    ProductStockAdjustView,
    CartListView,
    AddToCartView,
    UpdateCartItemView,
    RemoveCartItemView,
    CheckoutPreviewView,
    CheckoutCreateOrderView,
    OrderListView,
    OrderDetailView,
    session_to_jwt,
    mobile_bridge,
)

app_name = "bika_api"

urlpatterns = [
    # ==================== USER / DASHBOARD ====================
    path("me/", MeView.as_view(), name="api_me"),
    path("dashboard/summary/", DashboardSummaryView.as_view(), name="api_dashboard_summary"),

    # ==================== PRODUCTS ====================
    path("products/", ProductListView.as_view(), name="api_products_list"),                 # GET
    path("products/create/", ProductCreateView.as_view(), name="api_products_create"),      # POST
    path("products/<int:id>/", ProductDetailView.as_view(), name="api_products_detail"),    # GET
    path("products/<int:id>/update/", ProductUpdateView.as_view(), name="api_products_update"),  # PATCH/PUT
    path("products/<int:id>/delete/", ProductDeleteView.as_view(), name="api_products_delete"),  # DELETE
    path("products/<int:id>/stock/", ProductStockAdjustView.as_view(), name="api_products_stock"),  # PATCH

    # ==================== CART ====================
    path("cart/", CartListView.as_view(), name="api_cart_list"),                            # GET
    path("cart/add/", AddToCartView.as_view(), name="api_cart_add"),                        # POST
    path("cart/<int:item_id>/", UpdateCartItemView.as_view(), name="api_cart_update"),      # PATCH/PUT
    path("cart/<int:item_id>/remove/", RemoveCartItemView.as_view(), name="api_cart_remove"),  # DELETE/POST

    # ==================== CHECKOUT ====================
    path("checkout/preview/", CheckoutPreviewView.as_view(), name="api_checkout_preview"),
    path("checkout/create-order/", CheckoutCreateOrderView.as_view(), name="api_checkout_create_order"),

    # ==================== ORDERS ====================
    path("orders/", OrderListView.as_view(), name="api_orders_list"),
    path("orders/<int:id>/", OrderDetailView.as_view(), name="api_orders_detail"),

    # ==================== SESSION / MOBILE BRIDGE ====================
    path("session-to-jwt/", session_to_jwt, name="api_session_to_jwt"),
    path("mobile-bridge/", mobile_bridge, name="api_mobile_bridge"),
]