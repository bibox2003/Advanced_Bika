# bika/admin.py - UPDATED AND CORRECTED VERSION
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html
from django.db.models import Q,F, Count, Sum
from datetime import timedelta
from django.conf import settings
from django.contrib import messages
from django.urls import reverse
from .models import *
from django.contrib.admin.sites import NotRegistered

# ==================== DASHBOARD VIEW ====================

@staff_member_required
def admin_dashboard(request):
    """Enhanced admin dashboard with comprehensive statistics"""
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)
    
    # User Statistics
    user_stats = {
        'total': CustomUser.objects.count(),
        'today': CustomUser.objects.filter(date_joined__gte=today_start).count(),
        'yesterday': CustomUser.objects.filter(date_joined__gte=yesterday_start, date_joined__lt=today_start).count(),
        'admins': CustomUser.objects.filter(user_type='admin').count(),
        'vendors': CustomUser.objects.filter(user_type='vendor', is_active=True).count(),
        'customers': CustomUser.objects.filter(user_type='customer', is_active=True).count(),
        'active': CustomUser.objects.filter(is_active=True).count(),
        'inactive': CustomUser.objects.filter(is_active=False).count(),
    }
    
    # Product Statistics
    product_stats = {
        'total': Product.objects.count(),
        'active': Product.objects.filter(status='active').count(),
        'draft': Product.objects.filter(status='draft').count(),
        'out_of_stock': Product.objects.filter(stock_quantity=0, track_inventory=True).count(),
        'low_stock': Product.objects.filter(
            stock_quantity__gt=0,
            stock_quantity__lte=F('low_stock_threshold'),
            track_inventory=True
        ).count(),
        'featured': Product.objects.filter(is_featured=True, status='active').count(),
        'digital': Product.objects.filter(is_digital=True).count(),
        'today': Product.objects.filter(created_at__gte=today_start).count(),
    }
    
    # Order Statistics
    order_stats = {
        'total': Order.objects.count(),
        'pending': Order.objects.filter(status='pending').count(),
        'confirmed': Order.objects.filter(status='confirmed').count(),
        'shipped': Order.objects.filter(status='shipped').count(),
        'delivered': Order.objects.filter(status='delivered').count(),
        'cancelled': Order.objects.filter(status='cancelled').count(),
        'today': Order.objects.filter(created_at__gte=today_start).count(),
        'week': Order.objects.filter(created_at__gte=today_start - timedelta(days=7)).count(),
    }
    
    # Calculate revenue
    completed_orders = Order.objects.filter(status='delivered')
    total_revenue = sum(order.total_amount for order in completed_orders if order.total_amount)
    today_revenue = sum(
        order.total_amount for order in completed_orders.filter(
            created_at__gte=today_start
        ) if order.total_amount
    )
    
    # Payment Statistics
    payment_stats = {
        'total': Payment.objects.count(),
        'completed': Payment.objects.filter(status='completed').count(),
        'pending': Payment.objects.filter(status='pending').count(),
        'failed': Payment.objects.filter(status='failed').count(),
        'refunded': Payment.objects.filter(status='refunded').count(),
    }
    
    # Category Statistics
    category_stats = {
        'total': ProductCategory.objects.count(),
        'active': ProductCategory.objects.filter(is_active=True).count(),
        'with_products': ProductCategory.objects.filter(
            products__status='active'
        ).distinct().count(),
        'top_categories': ProductCategory.objects.annotate(
            product_count=Count('products', filter=Q(products__status='active'))
        ).order_by('-product_count')[:5],
    }
    
    # Fruit Monitoring Stats
    fruit_stats = {
        'batches': FruitBatch.objects.count(),
        'active_batches': FruitBatch.objects.filter(status='active').count(),
        'completed_batches': FruitBatch.objects.filter(status='completed').count(),
        'fruit_types': FruitType.objects.count(),
        'quality_readings': FruitQualityReading.objects.count(),
        'today_readings': FruitQualityReading.objects.filter(timestamp__gte=today_start).count(),
    }
    
    # Storage Stats
    storage_stats = {
        'locations': StorageLocation.objects.count(),
        'active_locations': StorageLocation.objects.filter(is_active=True).count(),
        'total_capacity': sum(location.capacity for location in StorageLocation.objects.all()),
        'total_occupancy': sum(location.current_occupancy for location in StorageLocation.objects.all()),
    }
    
    # Alert Stats
    alert_stats = {
        'total_alerts': ProductAlert.objects.count(),
        'unresolved_alerts': ProductAlert.objects.filter(is_resolved=False).count(),
        'critical_alerts': ProductAlert.objects.filter(severity='critical', is_resolved=False).count(),
        'high_alerts': ProductAlert.objects.filter(severity='high', is_resolved=False).count(),
    }
    
    # Recent Data
    recent_products = Product.objects.select_related(
        'vendor', 'category'
    ).prefetch_related('images').order_by('-created_at')[:6]
    
    recent_orders = Order.objects.select_related(
        'user'
    ).order_by('-created_at')[:5]
    
    recent_messages = ContactMessage.objects.filter(
        status='new'
    ).order_by('-submitted_at')[:5]
    
    recent_alerts = ProductAlert.objects.filter(
        is_resolved=False
    ).select_related('product').order_by('-created_at')[:5]
    
    # Activity Log (simplified)
    recent_activity = []
    
    # Get Django and Python version
    import django
    import sys
    django_version = django.get_version()
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    
    context = {
        # Statistics
        'user_stats': user_stats,
        'product_stats': product_stats,
        'order_stats': order_stats,
        'payment_stats': payment_stats,
        'category_stats': category_stats,
        'fruit_stats': fruit_stats,
        'storage_stats': storage_stats,
        'alert_stats': alert_stats,
        
        # Revenue
        'total_revenue': "{:,.2f}".format(total_revenue) if total_revenue else "0.00",
        'today_revenue': "{:,.2f}".format(today_revenue) if today_revenue else "0.00",
        
        # Recent Data
        'recent_products': recent_products,
        'recent_orders': recent_orders,
        'recent_messages': recent_messages,
        'recent_alerts': recent_alerts,
        'recent_activity': recent_activity,
        
        # Percentages for charts
        'admin_percentage': round((user_stats['admins'] / user_stats['total'] * 100), 2) if user_stats['total'] > 0 else 0,
        'vendor_percentage': round((user_stats['vendors'] / user_stats['total'] * 100), 2) if user_stats['total'] > 0 else 0,
        'customer_percentage': round((user_stats['customers'] / user_stats['total'] * 100), 2) if user_stats['total'] > 0 else 0,
        'active_products_percentage': round((product_stats['active'] / product_stats['total'] * 100), 2) if product_stats['total'] > 0 else 0,
        'active_users_percentage': round((user_stats['active'] / user_stats['total'] * 100), 2) if user_stats['total'] > 0 else 0,
        'completed_orders_percentage': round((order_stats['delivered'] / order_stats['total'] * 100), 2) if order_stats['total'] > 0 else 0,
        
        # Service stats
        'total_services': Service.objects.count(),
        'total_testimonials': Testimonial.objects.count(),
        'total_messages': ContactMessage.objects.count(),
        'new_messages': ContactMessage.objects.filter(status='new').count(),
        'active_services_count': Service.objects.filter(is_active=True).count(),
        'featured_testimonials_count': Testimonial.objects.filter(is_featured=True, is_active=True).count(),
        'active_faqs_count': FAQ.objects.filter(is_active=True).count(),
        
        # System info
        'django_version': django_version,
        'python_version': python_version,
        'debug': settings.DEBUG,
        'now': now,
    }
    
    return render(request, 'bika/pages/admin/dashboard.html', context)

# ==================== CUSTOM ADMIN ACTIONS ====================

class CustomAdminActions:
    """Custom admin actions for various models"""
    
    @staticmethod
    def mark_as_featured(modeladmin, request, queryset):
        queryset.update(is_featured=True)
        modeladmin.message_user(request, f"{queryset.count()} items marked as featured.")
    
    @staticmethod
    def mark_as_not_featured(modeladmin, request, queryset):
        queryset.update(is_featured=False)
        modeladmin.message_user(request, f"{queryset.count()} items marked as not featured.")
    
    @staticmethod
    def mark_as_active(modeladmin, request, queryset):
        queryset.update(is_active=True)
        modeladmin.message_user(request, f"{queryset.count()} items marked as active.")
    
    @staticmethod
    def mark_as_inactive(modeladmin, request, queryset):
        queryset.update(is_active=False)
        modeladmin.message_user(request, f"{queryset.count()} items marked as inactive.")
    
    @staticmethod
    def mark_as_approved(modeladmin, request, queryset):
        queryset.update(is_approved=True)
        modeladmin.message_user(request, f"{queryset.count()} items marked as approved.")
    
    @staticmethod
    def mark_as_resolved(modeladmin, request, queryset):
        queryset.update(is_resolved=True, resolved_at=timezone.now(), resolved_by=request.user)
        modeladmin.message_user(request, f"{queryset.count()} alerts marked as resolved.")
    
    @staticmethod
    def mark_as_read(modeladmin, request, queryset):
        queryset.update(is_read=True)
        modeladmin.message_user(request, f"{queryset.count()} notifications marked as read.")

# ==================== ADMIN MODEL REGISTRATIONS ====================

@admin.register(CustomUser)
class CustomUserAdmin(admin.ModelAdmin):
    list_display = ['username', 'email', 'user_type', 'is_active', 'is_staff', 'date_joined', 'action_buttons']
    list_filter = ['user_type', 'is_active', 'is_staff', 'date_joined']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'business_name']
    readonly_fields = ['date_joined', 'last_login']
    fieldsets = (
        ('Personal Info', {
            'fields': ('username', 'email', 'first_name', 'last_name', 'phone', 'profile_picture')
        }),
        ('User Type & Permissions', {
            'fields': ('user_type', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')
        }),
        ('Vendor Info', {
            'fields': ('business_name', 'business_description', 'business_logo', 'business_verified'),
            'classes': ('collapse',),
        }),
        ('Address', {
            'fields': ('company', 'address'),
            'classes': ('collapse',),
        }),
        ('Verification', {
            'fields': ('email_verified', 'phone_verified'),
            'classes': ('collapse',),
        }),
        ('Important Dates', {
            'fields': ('last_login', 'date_joined'),
            'classes': ('collapse',),
        }),
    )
    actions = ['activate_users', 'deactivate_users', 'make_vendors', 'make_customers']
    
    def action_buttons(self, obj):
        return format_html(
            '<a href="{}" class="button">View</a>',
            reverse('admin:bika_customuser_change', args=[obj.id])
        )
    action_buttons.short_description = 'Actions'
    
    def activate_users(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, f"{queryset.count()} users activated.")
    activate_users.short_description = "Activate selected users"
    
    def deactivate_users(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f"{queryset.count()} users deactivated.")
    deactivate_users.short_description = "Deactivate selected users"
    
    def make_vendors(self, request, queryset):
        queryset.update(user_type='vendor')
        self.message_user(request, f"{queryset.count()} users converted to vendors.")
    make_vendors.short_description = "Convert to vendors"
    
    def make_customers(self, request, queryset):
        queryset.update(user_type='customer')
        self.message_user(request, f"{queryset.count()} users converted to customers.")
    make_customers.short_description = "Convert to customers"

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'sku', 'category', 'vendor', 'price', 'stock_status', 
                   'status', 'is_featured', 'created_at', 'action_buttons']
    list_filter = ['status', 'category', 'vendor', 'is_featured', 'is_digital', 'created_at']
    search_fields = ['name', 'sku', 'description', 'short_description', 'tags']
    readonly_fields = ['created_at', 'updated_at', 'published_at', 'views_count']
    list_editable = ['status', 'is_featured']  # These are in list_display
    list_per_page = 20
    actions = ['activate_products', 'draft_products', 'mark_featured', 'unmark_featured']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'sku', 'barcode', 'category', 'vendor')
        }),
        ('Descriptions', {
            'fields': ('description', 'short_description', 'tags')
        }),
        ('Pricing', {
            'fields': ('price', 'compare_price', 'cost_price', 'tax_rate')
        }),
        ('Inventory', {
            'fields': ('stock_quantity', 'low_stock_threshold', 'track_inventory', 'allow_backorders')
        }),
        ('Product Details', {
            'fields': ('brand', 'model', 'weight', 'dimensions', 'color', 'size', 'material')
        }),
        ('Status & Visibility', {
            'fields': ('status', 'condition', 'is_featured', 'is_digital')
        }),
        ('SEO', {
            'fields': ('meta_title', 'meta_description'),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'published_at', 'views_count'),
            'classes': ('collapse',),
        }),
    )
    
    def stock_status(self, obj):
        if not obj.track_inventory:
            return format_html('<span class="badge badge-info">Not Tracked</span>')
        if obj.stock_quantity <= 0:
            return format_html('<span class="badge badge-danger">Out of Stock</span>')
        elif obj.stock_quantity <= obj.low_stock_threshold:
            return format_html('<span class="badge badge-warning">Low Stock</span>')
        else:
            return format_html('<span class="badge badge-success">In Stock</span>')
    stock_status.short_description = 'Stock'
    
    def action_buttons(self, obj):
        return format_html(
            '<a href="{}" class="button">View</a>',
            reverse('admin:bika_product_change', args=[obj.id])
        )
    action_buttons.short_description = 'Actions'
    
    def activate_products(self, request, queryset):
        updated = queryset.update(status='active')
        self.message_user(request, f"{updated} products activated.")
    activate_products.short_description = "Activate selected products"
    
    def draft_products(self, request, queryset):
        updated = queryset.update(status='draft')
        self.message_user(request, f"{updated} products moved to draft.")
    draft_products.short_description = "Move to draft"
    
    def mark_featured(self, request, queryset):
        updated = queryset.update(is_featured=True)
        self.message_user(request, f"{updated} products marked as featured.")
    mark_featured.short_description = "Mark as featured"
    
    def unmark_featured(self, request, queryset):
        updated = queryset.update(is_featured=False)
        self.message_user(request, f"{updated} products unmarked as featured.")
    unmark_featured.short_description = "Remove featured status"

# Safely unregister ProductCategory if it was already registered somewhere above
try:
    admin.site.unregister(ProductCategory)
except NotRegistered:
    pass


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'product_count', 'is_active', 'display_order']
    list_filter = ['is_active', 'parent']
    search_fields = ['name', 'description']
    list_editable = ['display_order', 'is_active']
    prepopulated_fields = {'slug': ('name',)}

    def product_count(self, obj):
        return obj.products.count()
    product_count.short_description = 'Products'

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ['product', 'image_preview', 'alt_text', 'display_order', 'is_primary']
    list_filter = ['is_primary', 'product']
    search_fields = ['product__name', 'alt_text']
    list_editable = ['display_order', 'is_primary']  # These are in list_display
    
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="50" height="50" />', obj.image.url)
        return "-"
    image_preview.short_description = 'Preview'

@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = ['product', 'user', 'rating_stars', 'title', 'is_approved', 
                   'is_verified_purchase', 'created_at']
    list_filter = ['rating', 'is_approved', 'is_verified_purchase', 'created_at']
    search_fields = ['product__name', 'user__username', 'title', 'comment']
    list_editable = ['is_approved']  # This is in list_display
    readonly_fields = ['created_at', 'updated_at']
    actions = ['approve_reviews', 'disapprove_reviews']
    
    def rating_stars(self, obj):
        stars = '★' * obj.rating + '☆' * (5 - obj.rating)
        return format_html('<span style="color: gold; font-size: 14px;">{}</span>', stars)
    rating_stars.short_description = 'Rating'
    
    def approve_reviews(self, request, queryset):
        queryset.update(is_approved=True)
        self.message_user(request, f"{queryset.count()} reviews approved.")
    approve_reviews.short_description = "Approve selected reviews"
    
    def disapprove_reviews(self, request, queryset):
        queryset.update(is_approved=False)
        self.message_user(request, f"{queryset.count()} reviews disapproved.")
    disapprove_reviews.short_description = "Disapprove selected reviews"

# ==================== E-COMMERCE MODELS ====================

@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ['user', 'product', 'added_at']
    list_filter = ['added_at']
    search_fields = ['user__username', 'product__name']
    readonly_fields = ['added_at']

@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['user', 'product', 'quantity', 'total_price', 'added_at']
    list_filter = ['added_at']
    search_fields = ['user__username', 'product__name']
    readonly_fields = ['added_at', 'updated_at']
    
    def total_price(self, obj):
        return f"${obj.total_price:.2f}" if obj.total_price else "$0.00"
    total_price.short_description = 'Total'

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'user', 'total_amount', 'status', 'created_at', 'action_buttons']
    list_filter = ['status', 'created_at']
    search_fields = ['order_number', 'user__username', 'shipping_address', 'billing_address']
    readonly_fields = ['created_at', 'updated_at', 'order_number']
    list_editable = ['status']  # This is in list_display
    actions = ['confirm_orders', 'ship_orders', 'deliver_orders', 'cancel_orders']
    
    def action_buttons(self, obj):
        return format_html(
            '<a href="{}" class="button">View</a>',
            reverse('admin:bika_order_change', args=[obj.id])
        )
    action_buttons.short_description = 'Actions'
    
    def confirm_orders(self, request, queryset):
        queryset.update(status='confirmed')
        self.message_user(request, f"{queryset.count()} orders confirmed.")
    confirm_orders.short_description = "Confirm selected orders"
    
    def ship_orders(self, request, queryset):
        queryset.update(status='shipped')
        self.message_user(request, f"{queryset.count()} orders marked as shipped.")
    ship_orders.short_description = "Mark as shipped"
    
    def deliver_orders(self, request, queryset):
        queryset.update(status='delivered')
        self.message_user(request, f"{queryset.count()} orders marked as delivered.")
    deliver_orders.short_description = "Mark as delivered"
    
    def cancel_orders(self, request, queryset):
        queryset.update(status='cancelled')
        self.message_user(request, f"{queryset.count()} orders cancelled.")
    cancel_orders.short_description = "Cancel selected orders"

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ['order', 'product', 'quantity', 'price', 'total_price']
    search_fields = ['order__order_number', 'product__name']
    
    def total_price(self, obj):
        return f"${obj.total_price:.2f}" if obj.total_price else "$0.00"
    total_price.short_description = 'Total'

# ==================== PAYMENT MODELS ====================

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['order', 'payment_method_display', 'amount', 'currency', 'status', 'created_at']
    list_filter = ['status', 'payment_method', 'currency', 'created_at']
    search_fields = ['order__order_number', 'transaction_id', 'mobile_money_phone']
    readonly_fields = ['created_at', 'updated_at', 'paid_at']
    
    def payment_method_display(self, obj):
        return obj.get_payment_method_display()
    payment_method_display.short_description = 'Payment Method'

@admin.register(PaymentGatewaySettings)
class PaymentGatewaySettingsAdmin(admin.ModelAdmin):
    list_display = ['gateway_display', 'is_active', 'environment', 'display_name']
    list_filter = ['is_active', 'environment', 'gateway']
    search_fields = ['display_name', 'gateway']
    readonly_fields = ['updated_at']
    
    def gateway_display(self, obj):
        return obj.get_gateway_display()
    gateway_display.short_description = 'Gateway'

@admin.register(CurrencyExchangeRate)
class CurrencyExchangeRateAdmin(admin.ModelAdmin):
    list_display = ['base_currency', 'target_currency', 'exchange_rate', 'last_updated']
    list_filter = ['base_currency', 'target_currency']
    search_fields = ['base_currency', 'target_currency']
    readonly_fields = ['last_updated']

# ==================== FRUIT MONITORING MODELS ====================

@admin.register(FruitType)
class FruitTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'scientific_name', 'optimal_temp_range', 'optimal_humidity_range', 
                   'shelf_life_days', 'batch_count']
    list_filter = ['ethylene_sensitive', 'chilling_sensitive']
    search_fields = ['name', 'scientific_name']
    list_editable = ['shelf_life_days']  # This is in list_display
    
    def optimal_temp_range(self, obj):
        return f"{obj.optimal_temp_min} - {obj.optimal_temp_max}°C"
    optimal_temp_range.short_description = 'Temperature Range'
    
    def optimal_humidity_range(self, obj):
        return f"{obj.optimal_humidity_min} - {obj.optimal_humidity_max}%"
    optimal_humidity_range.short_description = 'Humidity Range'
    
    def batch_count(self, obj):
        return obj.fruitbatch_set.count()
    batch_count.short_description = 'Batches'

@admin.register(FruitBatch)
class FruitBatchAdmin(admin.ModelAdmin):
    list_display = ['batch_number', 'fruit_type', 'quantity', 'arrival_date', 
                   'expected_expiry', 'days_remaining', 'status', 'current_quality']
    list_filter = ['status', 'fruit_type', 'arrival_date', 'storage_location']
    search_fields = ['batch_number', 'fruit_type__name', 'supplier']
    readonly_fields = ['created_at', 'updated_at']
    list_editable = ['status']  # This is in list_display
    
    def days_remaining(self, obj):
        return obj.days_remaining if hasattr(obj, 'days_remaining') else 0
    days_remaining.short_description = 'Days Remaining'
    
    def current_quality(self, obj):
        latest = FruitQualityReading.objects.filter(fruit_batch=obj).order_by('-timestamp').first()
        if latest:
            color = {
                'Fresh': 'success',
                'Good': 'info',
                'Fair': 'warning',
                'Poor': 'danger',
                'Rotten': 'dark',
            }.get(latest.predicted_class, 'secondary')
            return format_html(
                '<span class="badge badge-{}">{}</span>',
                color, latest.predicted_class
            )
        return '-'
    current_quality.short_description = 'Current Quality'

@admin.register(FruitQualityReading)
class FruitQualityReadingAdmin(admin.ModelAdmin):
    list_display = ['fruit_batch', 'timestamp', 'temperature', 'humidity', 
                   'predicted_class_badge', 'confidence_score', 'is_within_optimal_range']
    list_filter = ['predicted_class', 'timestamp', 'fruit_batch__fruit_type']
    search_fields = ['fruit_batch__batch_number', 'notes']
    readonly_fields = ['timestamp']
    list_per_page = 20
    
    def predicted_class_badge(self, obj):
        color = {
            'Fresh': 'success',
            'Good': 'info',
            'Fair': 'warning',
            'Poor': 'danger',
            'Rotten': 'dark',
        }.get(obj.predicted_class, 'secondary')
        return format_html(
            '<span class="badge badge-{}">{}</span>',
            color, obj.predicted_class
        )
    predicted_class_badge.short_description = 'Predicted Quality'
    
    def is_within_optimal_range(self, obj):
        return obj.is_within_optimal_range if hasattr(obj, 'is_within_optimal_range') else False
    is_within_optimal_range.boolean = True
    is_within_optimal_range.short_description = 'Optimal Range'

# ==================== STORAGE & SENSOR MODELS ====================

@admin.register(StorageLocation)
class StorageLocationAdmin(admin.ModelAdmin):
    list_display = ['name', 'address_short', 'capacity', 'current_occupancy', 
                   'available_capacity', 'occupancy_percentage', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'address']
    list_editable = ['is_active']  # This is in list_display
    
    def address_short(self, obj):
        if len(obj.address) > 30:
            return obj.address[:27] + '...'
        return obj.address
    address_short.short_description = 'Address'
    
    def available_capacity(self, obj):
        return obj.available_capacity if hasattr(obj, 'available_capacity') else 0
    available_capacity.short_description = 'Available'
    
    def occupancy_percentage(self, obj):
        if obj.capacity > 0:
            percentage = (obj.current_occupancy / obj.capacity) * 100
            color = 'success' if percentage < 80 else 'warning' if percentage < 95 else 'danger'
            return format_html(
                '<div class="progress" style="height: 20px; width: 100px;">'
                '<div class="progress-bar bg-{}" role="progressbar" '
                'style="width: {}%;" aria-valuenow="{}" aria-valuemin="0" '
                'aria-valuemax="100">{:.1f}%</div></div>',
                color, percentage, percentage, percentage
            )
        return '-'
    occupancy_percentage.short_description = 'Occupancy'

@admin.register(RealTimeSensorData)
class RealTimeSensorDataAdmin(admin.ModelAdmin):
    list_display = ['product', 'fruit_batch', 'sensor_type', 'value_with_unit', 
                   'location', 'recorded_at']
    list_filter = ['sensor_type', 'location', 'recorded_at']
    search_fields = ['product__name', 'fruit_batch__batch_number']
    readonly_fields = ['recorded_at']
    
    def value_with_unit(self, obj):
        return f"{obj.value} {obj.unit}" if obj.unit else str(obj.value)
    value_with_unit.short_description = 'Value'

# ==================== AI & DATASET MODELS ====================

@admin.register(ProductDataset)
class ProductDatasetAdmin(admin.ModelAdmin):
    list_display = ['name', 'dataset_type_display', 'row_count', 'is_active', 'created_at']
    list_filter = ['dataset_type', 'is_active', 'created_at']
    search_fields = ['name', 'description']
    
    def dataset_type_display(self, obj):
        return obj.get_dataset_type_display()
    dataset_type_display.short_description = 'Type'

@admin.register(TrainedModel)
class TrainedModelAdmin(admin.ModelAdmin):
    list_display = ['name', 'model_type_display', 'dataset', 'accuracy_percentage', 
                   'training_date', 'is_active']
    list_filter = ['model_type', 'is_active', 'training_date']
    search_fields = ['name', 'dataset__name']
    
    def model_type_display(self, obj):
        return obj.get_model_type_display()
    model_type_display.short_description = 'Model Type'
    
    def accuracy_percentage(self, obj):
        if obj.accuracy:
            return f"{obj.accuracy * 100:.2f}%"
        return '-'
    accuracy_percentage.short_description = 'Accuracy'

# ==================== ALERT & NOTIFICATION MODELS ====================

@admin.register(ProductAlert)
class ProductAlertAdmin(admin.ModelAdmin):
    list_display = ['product', 'alert_type_display', 'severity_badge', 'is_resolved', 
                   'created_at', 'resolved_at']
    list_filter = ['alert_type', 'severity', 'is_resolved', 'created_at']
    search_fields = ['product__name', 'message']
    readonly_fields = ['created_at', 'resolved_at']
    list_editable = ['is_resolved']  # This is in list_display
    actions = ['mark_resolved', 'mark_unresolved']
    
    def alert_type_display(self, obj):
        return obj.get_alert_type_display()
    alert_type_display.short_description = 'Alert Type'
    
    def severity_badge(self, obj):
        colors = {
            'low': 'info',
            'medium': 'warning',
            'high': 'danger',
            'critical': 'dark',
        }
        color = colors.get(obj.severity, 'secondary')
        return format_html(
            '<span class="badge badge-{}">{}</span>',
            color, obj.get_severity_display()
        )
    severity_badge.short_description = 'Severity'
    
    def mark_resolved(self, request, queryset):
        updated = queryset.update(is_resolved=True, resolved_at=timezone.now(), resolved_by=request.user)
        self.message_user(request, f"{updated} alerts marked as resolved.")
    mark_resolved.short_description = "Mark as resolved"
    
    def mark_unresolved(self, request, queryset):
        updated = queryset.update(is_resolved=False, resolved_at=None, resolved_by=None)
        self.message_user(request, f"{updated} alerts marked as unresolved.")
    mark_unresolved.short_description = "Mark as unresolved"

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'title', 'notification_type_display', 'is_read', 
                   'created_at', 'action_buttons']
    list_filter = ['notification_type', 'is_read', 'created_at']
    search_fields = ['user__username', 'title', 'message']
    readonly_fields = ['created_at']
    list_editable = ['is_read']  # This is in list_display
    actions = ['mark_read', 'mark_unread']
    
    def notification_type_display(self, obj):
        return obj.get_notification_type_display()
    notification_type_display.short_description = 'Type'
    
    def action_buttons(self, obj):
        return format_html(
            '<a href="{}" class="button">View</a>',
            reverse('admin:bika_notification_change', args=[obj.id])
        )
    action_buttons.short_description = 'Actions'
    
    def mark_read(self, request, queryset):
        updated = queryset.update(is_read=True)
        self.message_user(request, f"{updated} notifications marked as read.")
    mark_read.short_description = "Mark as read"
    
    def mark_unread(self, request, queryset):
        updated = queryset.update(is_read=False)
        self.message_user(request, f"{updated} notifications marked as unread.")
    mark_unread.short_description = "Mark as unread"

# ==================== SITE CONTENT MODELS ====================

@admin.register(SiteInfo)
class SiteInfoAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'phone', 'updated_at']
    readonly_fields = ['updated_at']
    
    def has_add_permission(self, request):
        # Allow only one instance
        if self.model.objects.count() >= 1:
            return False
        return super().has_add_permission(request)

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'display_order', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ['display_order', 'is_active']  # These are in list_display

@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ['name', 'company', 'rating_stars', 'is_featured', 'is_active', 'created_at']
    list_filter = ['is_featured', 'is_active', 'rating', 'created_at']
    search_fields = ['name', 'company', 'content']
    list_editable = ['is_featured', 'is_active']  # These are in list_display
    
    def rating_stars(self, obj):
        stars = '★' * obj.rating + '☆' * (5 - obj.rating)
        return format_html('<span style="color: gold; font-size: 14px;">{}</span>', stars)
    rating_stars.short_description = 'Rating'

@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ['name', 'email', 'subject', 'status', 'submitted_at', 'action_buttons']
    list_filter = ['status', 'submitted_at']
    search_fields = ['name', 'email', 'subject', 'message']
    readonly_fields = ['submitted_at', 'ip_address', 'replied_at']
    list_editable = ['status']  # This is in list_display
    actions = ['mark_as_replied', 'mark_as_read', 'mark_as_closed']
    
    def action_buttons(self, obj):
        return format_html(
            '<a href="{}" class="button">View</a>',
            reverse('admin:bika_contactmessage_change', args=[obj.id])
        )
    action_buttons.short_description = 'Actions'
    
    def mark_as_replied(self, request, queryset):
        for message in queryset:
            message.mark_as_replied()
        self.message_user(request, f"{queryset.count()} messages marked as replied.")
    mark_as_replied.short_description = "Mark as replied"
    
    def mark_as_read(self, request, queryset):
        queryset.update(status='read')
        self.message_user(request, f"{queryset.count()} messages marked as read.")
    mark_as_read.short_description = "Mark as read"
    
    def mark_as_closed(self, request, queryset):
        queryset.update(status='closed')
        self.message_user(request, f"{queryset.count()} messages marked as closed.")
    mark_as_closed.short_description = "Mark as closed"

@admin.register(FAQ)
class FAQAdmin(admin.ModelAdmin):
    list_display = ['question_short', 'answer_short', 'display_order', 'is_active', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['question', 'answer']
    list_editable = ['display_order', 'is_active']  # These are in list_display
    
    def question_short(self, obj):
        if len(obj.question) > 50:
            return obj.question[:47] + '...'
        return obj.question
    question_short.short_description = 'Question'
    
    def answer_short(self, obj):
        if len(obj.answer) > 50:
            return obj.answer[:47] + '...'
        return obj.answer
    answer_short.short_description = 'Answer'

# ==================== ADD DASHBOARD TO ADMIN ====================

# Add dashboard to admin URLs
def get_admin_urls():
    def wrap(view):
        def wrapper(*args, **kwargs):
            return admin.site.admin_view(view)(*args, **kwargs)
        return wrapper

    return [
        path('dashboard/', wrap(admin_dashboard), name='admin_dashboard'),
    ]

# Override admin site URLs to include dashboard
original_get_urls = admin.site.get_urls

def custom_get_urls():
    return get_admin_urls() + original_get_urls()

admin.site.get_urls = custom_get_urls

# Customize admin site
admin.site.site_header = "Bika Admin Dashboard"
admin.site.site_title = "Bika Admin"
admin.site.index_title = "Welcome to Bika Administration"

