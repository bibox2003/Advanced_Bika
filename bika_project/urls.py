# Bika_Project/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from bika import views

urlpatterns = [
    # ==================== CUSTOM ADMIN PAGES (MUST COME BEFORE 'admin/') ====================
    path("admin/ai-alerts/", views.ai_alert_dashboard, name="ai_alert_dashboard"),
    path("admin/model-management/", views.model_management, name="model_management"),
    path("admin/dashboard/", views.admin_dashboard, name="admin_dashboard"),
    path("admin/generate-sample-data/", views.generate_sample_data_view, name="generate_sample_data"),
    path("admin/scan-products/", views.scan_all_products_for_alerts, name="scan_products"),
    path("admin/train-new-model/", views.train_new_model_view, name="train_new_model"),
    path("admin/storage-sites/", views.storage_sites, name="storage_sites"),
    path("admin/activate-model/<int:model_id>/", views.activate_model, name="activate_model"),
    path("admin/product-ai-insights-overview/", views.product_ai_insights_overview, name="product_ai_insights_overview"),

    # ==================== API ROUTES FOR FLUTTER ====================
    path("api/", include("bika.api_urls")),

    # ==================== DJANGO ADMIN ====================
    path("admin/", admin.site.urls),

    # ==================== OTHER APP URLS ====================
    path("", include("bika.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
]

# Custom admin site text
admin.site.site_header = "Bika Administration"
admin.site.site_title = "Bika Admin Portal"
admin.site.index_title = "Welcome to Bika Admin Portal"

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Error handlers (single set only)
handler404 = "bika.views.handler404"
handler500 = "bika.views.handler500"
handler403 = "bika.views.handler403"
handler400 = "bika.views.handler400"
