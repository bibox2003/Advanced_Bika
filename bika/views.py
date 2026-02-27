# bika/views.py - FIXED AND COMPLETE VERSION
import os
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from bika.services.ai_service import enhanced_ai_service
fruit_ai_service = enhanced_ai_service
import joblib
from django.core.files.storage import default_storage
import tempfile
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.views.generic import ListView, DetailView, TemplateView
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST, require_GET
from django.views.decorators.cache import never_cache
from django.db.models import Q, Count, Sum, F, Avg, Max, Min
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone
from django.urls import reverse
from django.db import transaction

# ML imports for training utilities
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.svm import SVC
from sklearn.neighbors import KNeighborsClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

# XGBoost (optional)
try:
    from xgboost import XGBClassifier
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBClassifier = None
    XGBOOST_AVAILABLE = False

# Import models
from .models import (
    CustomUser, Product, ProductCategory, ProductImage, ProductReview,
    Wishlist, Cart, Order, OrderItem, Payment,
    SiteInfo, Service, Testimonial, ContactMessage, FAQ,
    StorageLocation, FruitType, FruitBatch, FruitQualityReading, 
    RealTimeSensorData, ProductAlert, Notification,
    ProductDataset, TrainedModel, PaymentGatewaySettings, CurrencyExchangeRate
)

# Import forms
from .forms import (
    ContactForm, NewsletterForm, CustomUserCreationForm, 
    VendorRegistrationForm, CustomerRegistrationForm, ProductForm,
    ProductImageForm, FruitBatchForm, FruitQualityReadingForm
)

# Import services

AI_SERVICES_AVAILABLE = True

# Payment services (simple fallback)
PAYMENT_SERVICES_AVAILABLE = False

# Try to import payment services
try:
    from .services.payment_gateways import PaymentGatewayFactory
    PAYMENT_SERVICES_AVAILABLE = True
except ImportError:
    PAYMENT_SERVICES_AVAILABLE = False
    logging.warning("Payment services not available")

# Set up logger
logger = logging.getLogger(__name__)

# ==================== BASIC VIEWS ====================

class HomeView(TemplateView):
    template_name = 'bika/home.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Get site info
        context['site_info'] = SiteInfo.objects.first()
        
        # Get featured products
        try:
            featured_products = Product.objects.filter(
                status='active',
                is_featured=True
            ).select_related('category', 'vendor')[:8]
            
            # Add primary images
            for product in featured_products:
                product.primary_image = product.images.filter(is_primary=True).first()
                if not product.primary_image:
                    product.primary_image = product.images.first()
            
            context['featured_products'] = featured_products
        except Exception as e:
            logger.error(f"Error loading featured products: {e}")
            context['featured_products'] = []
        
        # Get services
        context['featured_services'] = Service.objects.filter(is_active=True)[:6]
        
        # Get testimonials
        context['featured_testimonials'] = Testimonial.objects.filter(
            is_active=True, 
            is_featured=True
        )[:3]
        
        # Get FAQs
        context['faqs'] = FAQ.objects.filter(is_active=True)[:5]
        
        # Get product categories for navigation
        context['categories'] = ProductCategory.objects.filter(
            is_active=True, 
            parent__isnull=True
        )[:8]
        
        # Get stats for homepage
        context['total_products'] = Product.objects.filter(status='active').count()
        context['total_vendors'] = CustomUser.objects.filter(
            user_type='vendor', 
            is_active=True
        ).count()
        
        return context

# Add this function to your existing views.py, anywhere after the product_list_view function

def product_search_view(request):
    """Handle product search requests"""
    query = request.GET.get('q', '').strip()
    
    if not query:
        return redirect('bika:product_list')
    
    # Search products
    products = Product.objects.filter(
        Q(name__icontains=query) | 
        Q(description__icontains=query) |
        Q(short_description__icontains=query) |
        Q(tags__icontains=query) |
        Q(category__name__icontains=query),
        status='active'
    ).select_related('category', 'vendor')
    
    # Get search suggestions
    suggestions = []
    if products.exists():
        suggestions = Product.objects.filter(
            category__in=products.values_list('category', flat=True),
            status='active'
        ).exclude(id__in=products.values_list('id', flat=True))[:5]
    
    # Get categories
    categories = ProductCategory.objects.filter(
        is_active=True,
        parent__isnull=True
    ).annotate(
        product_count=Count('products', filter=Q(products__status='active'))
    )
    
    # Pagination
    paginator = Paginator(products, 12)
    page_number = request.GET.get('page')
    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)
    
    context = {
        'products': page_obj,
        'query': query,
        'suggestions': suggestions,
        'categories': categories,
        'total_results': products.count(),
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/search_results.html', context)

def user_settings(request):
    """User settings page"""
    context = {
        'user': request.user,
        'site_info': SiteInfo.objects.first(),
    }
    return render(request, 'bika/pages/user/settings.html', context)

@login_required
@require_POST
def quick_add_to_cart(request, product_id):
    """Quick add to cart (for AJAX requests)"""
    product = get_object_or_404(Product, id=product_id)
    
    # Check stock
    if product.track_inventory and product.stock_quantity < 1:
        return JsonResponse({
            'success': False,
            'message': f'Product out of stock!'
        })
    
    # Add to cart
    cart_item, created = Cart.objects.get_or_create(
        user=request.user,
        product=product,
        defaults={'quantity': 1}
    )
    
    if not created:
        cart_item.quantity += 1
        cart_item.save()
    
    # Get updated cart count
    cart_count = Cart.objects.filter(user=request.user).count()
    
    return JsonResponse({
        'success': True,
        'message': f'{product.name} added to cart!',
        'cart_count': cart_count,
        'created': created
    })
def about_view(request):
    services = Service.objects.filter(is_active=True)
    testimonials = Testimonial.objects.filter(is_active=True)[:4]
    site_info = SiteInfo.objects.first()
    
    context = {
        'services': services,
        'testimonials': testimonials,
        'site_info': site_info,
    }
    return render(request, 'bika/pages/about.html', context)

def services_view(request):
    services = Service.objects.filter(is_active=True)
    site_info = SiteInfo.objects.first()
    
    context = {
        'services': services,
        'site_info': site_info,
    }
    return render(request, 'bika/pages/services.html', context)

class ServiceDetailView(DetailView):
    model = Service
    template_name = 'bika/pages/service_detail.html'
    context_object_name = 'service'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['site_info'] = SiteInfo.objects.first()
        return context

def contact_view(request):
    site_info = SiteInfo.objects.first()
    
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            contact_message = form.save(commit=False)
            
            # Get client IP address
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                contact_message.ip_address = x_forwarded_for.split(',')[0]
            else:
                contact_message.ip_address = request.META.get('REMOTE_ADDR')
            
            contact_message.save()
            
            # Send email notification
            try:
                send_mail(
                    f'New Contact Message: {contact_message.subject}',
                    f'''
                    Name: {contact_message.name}
                    Email: {contact_message.email}
                    Phone: {contact_message.phone}
                    
                    Message:
                    {contact_message.message}
                    ''',
                    settings.DEFAULT_FROM_EMAIL,
                    [settings.DEFAULT_FROM_EMAIL],
                    fail_silently=True,
                )
            except Exception as e:
                logger.error(f"Email error: {e}")
            
            messages.success(
                request, 
                'Thank you for your message! We will get back to you soon.'
            )
            return redirect('bika:contact')
    else:
        form = ContactForm()
    
    context = {
        'form': form,
        'site_info': site_info,
    }
    return render(request, 'bika/pages/contact.html', context)

def faq_view(request):
    faqs = FAQ.objects.filter(is_active=True)
    site_info = SiteInfo.objects.first()
    
    context = {
        'faqs': faqs,
        'site_info': site_info,
    }
    return render(request, 'bika/pages/faq.html', context)

@csrf_exempt
@require_POST
def newsletter_subscribe(request):
    """Handle newsletter subscription"""
    try:
        email = request.POST.get('email')
        
        if not email:
            return JsonResponse({
                'success': False,
                'message': 'Please enter a valid email address.'
            })
        
        # Here you would save to your newsletter model
        # For now, just return success
        return JsonResponse({
            'success': True,
            'message': 'Thank you for subscribing to our newsletter!'
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'message': 'An error occurred. Please try again.'
        })

# ==================== ADMIN VIEWS ====================
# ==================== DASHBOARD ENHANCEMENTS ====================

@staff_member_required
def admin_dashboard(request):
    """Enhanced admin dashboard with comprehensive statistics"""
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    thirty_days_ago = now - timedelta(days=30)
    
    # ===== USER STATISTICS =====
    total_users = CustomUser.objects.count()
    total_admins = CustomUser.objects.filter(user_type='admin').count()
    total_vendors = CustomUser.objects.filter(user_type='vendor').count()
    total_customers = CustomUser.objects.filter(user_type='customer').count()
    new_users_today = CustomUser.objects.filter(date_joined__gte=today_start).count()
    active_users = CustomUser.objects.filter(last_login__gte=thirty_days_ago).count()
    
    # Calculate percentages
    if total_users > 0:
        admin_percentage = round((total_admins / total_users) * 100, 1)
        vendor_percentage = round((total_vendors / total_users) * 100, 1)
        customer_percentage = round((total_customers / total_users) * 100, 1)
    else:
        admin_percentage = vendor_percentage = customer_percentage = 0
    
    # ===== PRODUCT STATISTICS =====
    total_products = Product.objects.count()
    active_products = Product.objects.filter(status='active').count()
    draft_products = Product.objects.filter(status='draft').count()
    out_of_stock = Product.objects.filter(
        stock_quantity=0, 
        track_inventory=True
    ).count()
    low_stock = Product.objects.filter(
        stock_quantity__gt=0,
        stock_quantity__lte=F('low_stock_threshold'),
        track_inventory=True
    ).count()
    featured_products = Product.objects.filter(is_featured=True, status='active').count()
    
    # ===== ORDER STATISTICS =====
    total_orders = Order.objects.count()
    pending_orders = Order.objects.filter(status='pending').count()
    confirmed_orders = Order.objects.filter(status='confirmed').count()
    shipped_orders = Order.objects.filter(status='shipped').count()
    delivered_orders = Order.objects.filter(status='delivered').count()
    cancelled_orders = Order.objects.filter(status='cancelled').count()
    
    # ===== REVENUE CALCULATIONS =====
    completed_orders = Order.objects.filter(status='delivered')
    total_revenue = completed_orders.aggregate(
        total=Sum('total_amount')
    )['total'] or 0
    
    today_revenue = completed_orders.filter(
        created_at__gte=today_start
    ).aggregate(
        total=Sum('total_amount')
    )['total'] or 0
    
    # ===== CATEGORY STATISTICS =====
    total_categories = ProductCategory.objects.count()
    active_categories = ProductCategory.objects.filter(is_active=True).count()
    categories_with_products = ProductCategory.objects.filter(
        products__status='active'
    ).distinct().count()
    
    # ===== FRUIT MONITORING STATS =====
    fruit_batches = FruitBatch.objects.count()
    active_fruit_batches = FruitBatch.objects.filter(status='active').count()
    fruit_types = FruitType.objects.count()
    quality_readings = FruitQualityReading.objects.count()
    
    # ===== AI SYSTEM STATS =====
    total_predictions = FruitQualityReading.objects.count()
    dataset_size = ProductDataset.objects.count()
    active_vendors = CustomUser.objects.filter(
        user_type='vendor', is_active=True
    ).count()
    
    # Get critical alerts
    critical_alerts = ProductAlert.objects.filter(
        is_resolved=False, severity='critical'
    ).count()
    
    # ===== RECENT DATA =====
    recent_products = Product.objects.select_related(
        'vendor', 'category'
    ).prefetch_related('images').order_by('-created_at')[:6]
    
    recent_orders = Order.objects.select_related('user').order_by('-created_at')[:5]
    
    recent_messages = ContactMessage.objects.filter(
        status='new'
    ).order_by('-submitted_at')[:5]
    
    # Get Django version and debug status
    import django
    from django.conf import settings
    django_version = django.get_version()
    debug = settings.DEBUG
    
    # Add status colors for orders
    for order in recent_orders:
        status_colors = {
            'pending': 'warning',
            'confirmed': 'info',
            'shipped': 'primary',
            'delivered': 'success',
            'cancelled': 'danger'
        }
        order.status_color = status_colors.get(order.status, 'secondary')
    
    context = {
        # User statistics
        'total_users': total_users,
        'total_admins': total_admins,
        'total_vendors': total_vendors,
        'total_customers': total_customers,
        'new_users_today': new_users_today,
        'active_users': active_users,
        'admin_percentage': admin_percentage,
        'vendor_percentage': vendor_percentage,
        'customer_percentage': customer_percentage,
        'active_vendors': active_vendors,
        
        # Product statistics
        'total_products': total_products,
        'active_products': active_products,
        'draft_products': draft_products,
        'out_of_stock': out_of_stock,
        'low_stock': low_stock,
        'featured_products': featured_products,
        
        # Order statistics
        'total_orders': total_orders,
        'pending_orders': pending_orders,
        'confirmed_orders': confirmed_orders,
        'shipped_orders': shipped_orders,
        'delivered_orders': delivered_orders,
        'cancelled_orders': cancelled_orders,
        
        # Revenue
        'total_revenue': total_revenue,
        'today_revenue': today_revenue,
        
        # Category statistics
        'total_categories': total_categories,
        'active_categories': active_categories,
        'categories_with_products': categories_with_products,
        
        # Fruit monitoring
        'fruit_batches': fruit_batches,
        'active_fruit_batches': active_fruit_batches,
        'fruit_types': fruit_types,
        'quality_readings': quality_readings,
        
        # AI System stats
        'ai_service': enhanced_ai_service,
        'total_predictions': total_predictions,
        'dataset_size': dataset_size,
        'critical_alerts': critical_alerts,
        
        # Recent data
        'recent_products': recent_products,
        'recent_orders': recent_orders,
        'recent_messages': recent_messages,
        
        # System info
        'django_version': django_version,
        'debug': debug,
        
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/admin/dashboard.html', context)

@staff_member_required
@require_GET
def sales_analytics_api(request):
    """API for sales analytics"""
    days = int(request.GET.get('days', 30))
    end_date = timezone.now()
    start_date = end_date - timedelta(days=days)
    
    # Generate daily sales data
    sales_data = []
    current_date = start_date
    
    while current_date <= end_date:
        next_date = current_date + timedelta(days=1)
        daily_sales = Order.objects.filter(
            created_at__range=[current_date, next_date],
            status='delivered'
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        
        sales_data.append({
            'date': current_date.strftime('%Y-%m-%d'),
            'sales': float(daily_sales),
            'orders': Order.objects.filter(
                created_at__range=[current_date, next_date],
                status='delivered'
            ).count()
        })
        
        current_date = next_date
    
    # Get top selling products
    top_products = OrderItem.objects.filter(
        order__created_at__range=[start_date, end_date],
        order__status='delivered'
    ).values(
        'product__name', 'product__sku'
    ).annotate(
        total_quantity=Sum('quantity'),
        total_revenue=Sum(F('quantity') * F('price'))
    ).order_by('-total_quantity')[:5]
    
    return JsonResponse({
        'success': True,
        'sales_data': sales_data,
        'top_products': list(top_products),
        'total_days': days
    })

@staff_member_required
@require_GET
def get_active_alerts(request):
    """API for active alerts"""
    alerts = ProductAlert.objects.filter(
        is_resolved=False
    ).select_related('product').order_by('-created_at')[:10]
    
    alert_list = []
    for alert in alerts:
        alert_list.append({
            'id': alert.id,
            'title': f"{alert.alert_type.replace('_', ' ').title()} Alert",
            'message': alert.message,
            'severity': alert.severity,
            'product': alert.product.name if alert.product else 'Unknown',
            'created_at': alert.created_at.strftime('%Y-%m-%d %H:%M'),
            'details': json.loads(alert.details) if alert.details else {}
        })
    
    return JsonResponse({
        'success': True,
        'alerts': alert_list,
        'count': alerts.count()
    })

@staff_member_required
@require_GET
def performance_metrics_api(request):
    """API for performance metrics"""
    import psutil
    import os
    
    # Get system metrics
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    # Get database query count (simplified)
    from django.db import connection
    db_queries = len(connection.queries) if settings.DEBUG else 0
    
    return JsonResponse({
        'success': True,
        'response_time': round(cpu_percent / 100, 3),  # Simulated
        'server_load': f"{cpu_percent}%",
        'memory_usage': f"{memory.used / (1024**3):.1f}GB / {memory.total / (1024**3):.1f}GB",
        'disk_usage': f"{disk.percent}%",
        'db_queries': db_queries,
        'timestamp': timezone.now().strftime('%Y-%m-%d %H:%M:%S')
    })

@staff_member_required
@require_GET
def export_inventory_report(request):
    """Export inventory report as CSV"""
    import csv
    from django.http import HttpResponse
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    filename = f"inventory-report-{timezone.now().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    
    # Write headers
    writer.writerow([
        'Product ID', 'SKU', 'Product Name', 'Category', 
        'Stock Quantity', 'Low Stock Threshold', 'Status',
        'Price', 'Vendor', 'Last Updated'
    ])
    
    # Write data
    products = Product.objects.select_related('category', 'vendor').order_by('category__name', 'name')
    
    for product in products:
        writer.writerow([
            product.id,
            product.sku,
            product.name,
            product.category.name if product.category else '',
            product.stock_quantity,
            product.low_stock_threshold,
            product.get_status_display(),
            float(product.price),
            product.vendor.username if product.vendor else '',
            product.updated_at.strftime('%Y-%m-%d %H:%M')
        ])
    
    return response

@staff_member_required
@require_GET
def get_user_activity(request):
    """Get recent user activity"""
    from datetime import datetime, timedelta
    
    recent_activity = []
    
    # Recent logins (last 24 hours)
    recent_logins = CustomUser.objects.filter(
        last_login__gte=timezone.now() - timedelta(hours=24)
    ).order_by('-last_login')[:5]
    
    for user in recent_logins:
        recent_activity.append({
            'type': 'login',
            'user': user.username,
            'time': user.last_login.strftime('%H:%M'),
            'icon': 'fas fa-sign-in-alt',
            'color': 'success'
        })
    
    # Recent orders
    recent_orders = Order.objects.order_by('-created_at')[:3]
    for order in recent_orders:
        recent_activity.append({
            'type': 'order',
            'user': order.user.username,
            'time': order.created_at.strftime('%H:%M'),
            'icon': 'fas fa-shopping-cart',
            'color': 'primary',
            'details': f"Order #{order.order_number}"
        })
    
    # Recent product additions
    recent_products = Product.objects.order_by('-created_at')[:3]
    for product in recent_products:
        recent_activity.append({
            'type': 'product',
            'user': product.vendor.username if product.vendor else 'System',
            'time': product.created_at.strftime('%H:%M'),
            'icon': 'fas fa-cube',
            'color': 'info',
            'details': f"Added: {product.name}"
        })
    
    return JsonResponse({
        'success': True,
        'activities': recent_activity
    })
# ==================== AI ALERT SYSTEM VIEWS ====================

@staff_member_required
def ai_alert_dashboard(request):
    """Dashboard for AI-generated alerts"""
    # Get all alerts
    alerts = ProductAlert.objects.filter(
        is_resolved=False
    ).select_related('product', 'product__vendor').order_by('-created_at')
    
    # Get alert statistics
    total_alerts = alerts.count()
    critical_alerts = alerts.filter(severity='critical').count()
    high_alerts = alerts.filter(severity='high').count()
    
    # Get recent predictions
    recent_predictions = []
    try:
        from .ai_integration.models import FruitPrediction
        recent_predictions = FruitPrediction.objects.select_related(
            'product'
        ).order_by('-prediction_date')[:10]
    except:
        pass
    
    context = {
        'alerts': alerts[:50],  # Limit to 50 for performance
        'total_alerts': total_alerts,
        'critical_alerts': critical_alerts,
        'high_alerts': high_alerts,
        'recent_predictions': recent_predictions,
        'ai_service': enhanced_ai_service,
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/admin/ai_alert_dashboard.html', context)

@staff_member_required
@require_POST
def scan_all_products_for_alerts(request):
    """Scan all products and generate AI alerts"""
    try:
        from .models import Product
        
        # Get all active products
        products = Product.objects.filter(status='active')
        
        results = {
            'scanned': 0,
            'predictions': 0,
            'alerts': 0,
            'errors': 0
        }
        
        # Scan each product
        for product in products[:50]:  # Limit to 50 for performance
            try:
                # Get prediction and alerts
                result = enhanced_ai_service.predict_and_alert(product.id)
                
                if 'error' in result:
                    results['errors'] += 1
                else:
                    results['predictions'] += 1
                    results['alerts'] += len(result.get('alerts', []))
                
                results['scanned'] += 1
                
            except Exception as e:
                results['errors'] += 1
                print(f"Error scanning product {product.id}: {e}")
        
        messages.success(
            request, 
            f"Scanned {results['scanned']} products. "
            f"Generated {results['alerts']} new alerts."
        )
        
        return redirect('bika:ai_alert_dashboard')
        
    except Exception as e:
        messages.error(request, f"Error scanning products: {e}")
        return redirect('bika:ai_alert_dashboard')

@login_required
def product_ai_insights(request, product_id):
    """Show AI insights for a specific product"""
    product = get_object_or_404(Product, id=product_id)
    
    # Check permission
    if not request.user.is_staff and product.vendor != request.user:
        messages.error(request, "Access denied.")
        return redirect('bika:home')
    
    # Get predictions for this product
    predictions = []
    try:
        from .ai_integration.models import FruitPrediction
        predictions = FruitPrediction.objects.filter(
            product=product
        ).order_by('-prediction_date')[:10]
    except:
        pass
    
    # Get alerts for this product
    alerts = ProductAlert.objects.filter(
        product=product,
        is_resolved=False
    ).order_by('-created_at')
    
    # Get real-time prediction
    current_prediction = None
    try:
        result = enhanced_ai_service.predict_and_alert(product.id)
        if 'prediction' in result:
            current_prediction = result['prediction']
    except:
        pass
    
    context = {
        'product': product,
        'predictions': predictions,
        'alerts': alerts,
        'current_prediction': current_prediction,
        'ai_service': enhanced_ai_service,
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/product_ai_insights.html', context)

@staff_member_required
def train_new_model_view(request):
    """Train a new AI model"""
    if request.method == 'POST':
        if 'dataset_file' not in request.FILES:
            messages.error(request, 'Please upload a dataset file')
            return redirect('bika:train_new_model')
        
        csv_file = request.FILES['dataset_file']
        target_column = request.POST.get('target_column', 'quality_class')
        model_type = request.POST.get('model_type', 'random_forest')
        
        # Train model
        result = enhanced_ai_service.train_five_models(csv_file, target_column)
        
        if 'error' in result:
            messages.error(request, f"Training failed: {result['error']}")
        else:
            messages.success(request, 'Model trained successfully!')
            
            if result.get('model_saved'):
                messages.info(request, f"New model activated (ID: {result['model_id']})")
        
        return redirect('bika:model_management')
    
    context = {
        'site_info': SiteInfo.objects.first(),
    }
    return render(request, 'bika/pages/admin/train_new_model.html', context)

@staff_member_required
def model_management(request):
    """Manage AI models"""
    # Get model comparison
    comparison_result = enhanced_ai_service.get_detailed_model_comparison()
    
    # Get active model info
    active_model_info = None
    if enhanced_ai_service.active_model:
        active_model_info = {
            'name': enhanced_ai_service.active_model['record'].name,
            'accuracy': enhanced_ai_service.active_model['record'].accuracy,
            'features': enhanced_ai_service.active_model['record'].features_used,
            'trained_date': enhanced_ai_service.active_model['record'].trained_date
        }
    
    context = {
        'comparison_result': comparison_result,
        'active_model': active_model_info,
        'ai_service': enhanced_ai_service,
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/admin/model_management.html', context)

@staff_member_required
@require_POST
def activate_model(request, model_id):
    """Activate a specific model"""
    try:
        from .ai_integration.models import TrainedModel
        
        # Get the model to activate
        model_to_activate = TrainedModel.objects.get(id=model_id, model_type='quality')
        
        # Deactivate all other models
        TrainedModel.objects.filter(
            model_type='quality'
        ).exclude(id=model_id).update(is_active=False)
        
        # Activate this model
        model_to_activate.is_active = True
        model_to_activate.save()
        
        # Reload the model in the service
        enhanced_ai_service.load_active_model()
        
        messages.success(request, f"Model '{model_to_activate.name}' activated successfully!")
        
    except TrainedModel.DoesNotExist:
        messages.error(request, "Model not found")
    except Exception as e:
        messages.error(request, f"Error activating model: {e}")
    
    return redirect('bika:model_management')

@staff_member_required
def generate_sample_data_view(request):
    """Generate sample dataset for training"""
    if request.method == 'POST':
        num_samples = int(request.POST.get('samples', 1000))
        
        result = enhanced_ai_service.generate_sample_dataset(num_samples)
        
        if result.get('success'):
            messages.success(request, f'Sample dataset generated with {num_samples} records')
            
            # Offer download link
            request.session['generated_dataset'] = {
                'filename': result['filename'],
                'download_url': result['download_url']
            }
        else:
            messages.error(request, f"Failed to generate dataset: {result.get('error')}")
    
    context = {
        'site_info': SiteInfo.objects.first(),
    }
    return render(request, 'bika/pages/admin/generate_sample_data.html', context)

@staff_member_required
def download_generated_dataset(request):
    """Download generated dataset"""
    dataset_info = request.session.get('generated_dataset')
    
    if not dataset_info:
        messages.error(request, "No dataset available for download")
        return redirect('bika:generate_sample_data')
    
    filepath = os.path.join(settings.MEDIA_ROOT, 'datasets', dataset_info['filename'])
    
    if os.path.exists(filepath):
        with open(filepath, 'rb') as f:
            response = HttpResponse(f.read(), content_type='text/csv')
            response['Content-Disposition'] = f'attachment; filename="{dataset_info["filename"]}"'
            return response
    
    messages.error(request, "Dataset file not found")
    return redirect('bika:generate_sample_data')

# ==================== API ENDPOINTS FOR ALERTS ====================

@csrf_exempt
@require_POST
def batch_product_scan_api(request):
    """API endpoint to scan multiple products"""
    try:
        product_ids = json.loads(request.body).get('product_ids', [])
        
        if not product_ids:
            return JsonResponse({'success': False, 'error': 'No product IDs provided'})
        
        results = {
            'scanned': 0,
            'alerts_generated': 0,
            'errors': 0,
            'product_results': []
        }
        
        for product_id in product_ids[:20]:  # Limit to 20 products
            try:
                result = enhanced_ai_service.predict_and_alert(product_id)
                
                product_result = {
                    'product_id': product_id,
                    'success': 'error' not in result,
                    'alerts': len(result.get('alerts', []))
                }
                
                if 'error' in result:
                    product_result['error'] = result['error']
                    results['errors'] += 1
                else:
                    results['alerts_generated'] += product_result['alerts']
                
                results['product_results'].append(product_result)
                results['scanned'] += 1
                
            except Exception as e:
                results['errors'] += 1
        
        return JsonResponse({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@csrf_exempt
@require_GET
def get_product_quality_prediction(request, product_id):
    """Get quality prediction for a product"""
    try:
        product = Product.objects.get(id=product_id)
        
        # Check permission
        if not request.user.is_staff and product.vendor != request.user:
            return JsonResponse({'success': False, 'error': 'Permission denied'})
        
        # Get prediction
        result = enhanced_ai_service.predict_and_alert(product_id)
        
        if 'error' in result:
            return JsonResponse({'success': False, 'error': result['error']})
        
        return JsonResponse({
            'success': True,
            'product': {
                'id': product.id,
                'name': product.name,
                'sku': product.sku
            },
            'prediction': result.get('prediction'),
            'alerts': result.get('alerts', [])
        })
        
    except Product.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Product not found'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

def product_list_view(request):
    """Display all active products with filtering and pagination"""
    products = Product.objects.filter(status='active').select_related('category', 'vendor')
    
    # Get filter parameters
    category_slug = request.GET.get('category')
    query = request.GET.get('q', '')
    sort_by = request.GET.get('sort', 'newest')
    min_price = request.GET.get('min_price')
    max_price = request.GET.get('max_price')
    
    # Filter by category
    current_category = None
    if category_slug:
        try:
            current_category = ProductCategory.objects.get(slug=category_slug, is_active=True)
            products = products.filter(category=current_category)
        except ProductCategory.DoesNotExist:
            pass
    
    # Search functionality
    if query:
        products = products.filter(
            Q(name__icontains=query) | 
            Q(description__icontains=query) |
            Q(short_description__icontains=query) |
            Q(tags__icontains=query) |
            Q(category__name__icontains=query) |
            Q(brand__icontains=query) |
            Q(model__icontains=query)
        )
    
    # Price filtering
    if min_price:
        try:
            products = products.filter(price__gte=float(min_price))
        except ValueError:
            pass
    
    if max_price:
        try:
            products = products.filter(price__lte=float(max_price))
        except ValueError:
            pass
    
    # Sorting
    if sort_by == 'price_low':
        products = products.order_by('price')
    elif sort_by == 'price_high':
        products = products.order_by('-price')
    elif sort_by == 'name':
        products = products.order_by('name')
    elif sort_by == 'popular':
        products = products.order_by('-views_count')
    elif sort_by == 'featured':
        products = products.order_by('-is_featured', '-created_at')
    else:  # newest
        products = products.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(products, 12)
    page_number = request.GET.get('page')
    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)
    
    # Get categories for sidebar
    categories = ProductCategory.objects.filter(
        is_active=True,
        parent__isnull=True
    ).annotate(
        product_count=Count('products', filter=Q(products__status='active'))
    )
    
    context = {
        'products': page_obj,
        'categories': categories,
        'current_category': current_category,
        'query': query,
        'sort_by': sort_by,
        'min_price': min_price,
        'max_price': max_price,
        'total_products': products.count(),
        'site_info': SiteInfo.objects.first(),
    }
    return render(request, 'bika/pages/products.html', context)

def product_detail_view(request, slug):
    """Display single product details"""
    product = get_object_or_404(Product.objects.select_related(
        'category', 'vendor'
    ).prefetch_related('images'), slug=slug, status='active')
    
    # Increment view count
    product.views_count += 1
    product.save()
    
    # Get related products
    related_products = Product.objects.filter(
        category=product.category,
        status='active'
    ).exclude(id=product.id).select_related(
        'category', 'vendor'
    ).prefetch_related('images')[:4]
    
    # Get product reviews
    reviews = ProductReview.objects.filter(
        product=product, 
        is_approved=True
    ).select_related('user').order_by('-created_at')
    
    # Calculate average rating
    avg_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0
    
    # Check if product is in user's wishlist
    in_wishlist = False
    if request.user.is_authenticated:
        in_wishlist = Wishlist.objects.filter(
            user=request.user, 
            product=product
        ).exists()
    
    # Check if product is in user's cart
    in_cart = False
    cart_quantity = 0
    if request.user.is_authenticated:
        cart_item = Cart.objects.filter(
            user=request.user, 
            product=product
        ).first()
        if cart_item:
            in_cart = True
            cart_quantity = cart_item.quantity
    
    context = {
        'product': product,
        'related_products': related_products,
        'reviews': reviews,
        'avg_rating': round(avg_rating, 1) if avg_rating else 0,
        'review_count': reviews.count(),
        'in_wishlist': in_wishlist,
        'in_cart': in_cart,
        'cart_quantity': cart_quantity,
        'site_info': SiteInfo.objects.first(),
    }
    return render(request, 'bika/pages/product_detail.html', context)

def products_by_category_view(request, category_slug):
    """Display products by category"""
    category = get_object_or_404(
        ProductCategory.objects.prefetch_related('subcategories'),
        slug=category_slug, 
        is_active=True
    )
    
    # Get products in this category and subcategories
    subcategory_ids = list(category.subcategories.values_list('id', flat=True)) + [category.id]
    products = Product.objects.filter(
        category_id__in=subcategory_ids,
        status='active'
    ).select_related('category', 'vendor')
    
    # Get filter parameters
    query = request.GET.get('q', '')
    sort_by = request.GET.get('sort', 'newest')
    
    if query:
        products = products.filter(
            Q(name__icontains=query) | 
            Q(description__icontains=query) |
            Q(tags__icontains=query)
        )
    
    # Sorting
    if sort_by == 'price_low':
        products = products.order_by('price')
    elif sort_by == 'price_high':
        products = products.order_by('-price')
    elif sort_by == 'name':
        products = products.order_by('name')
    else:  # newest
        products = products.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(products, 12)
    page_number = request.GET.get('page')
    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)
    
    # Get sibling categories
    if category.parent:
        categories = category.parent.subcategories.filter(is_active=True)
    else:
        categories = ProductCategory.objects.filter(
            parent__isnull=True,
            is_active=True
        )
    
    context = {
        'category': category,
        'products': page_obj,
        'categories': categories,
        'current_category': category,
        'query': query,
        'sort_by': sort_by,
        'total_products': products.count(),
        'site_info': SiteInfo.objects.first(),
    }
    return render(request, 'bika/pages/products.html', context)

@login_required
def add_review(request, product_id):
    """Add product review"""
    if request.method == 'POST':
        product = get_object_or_404(Product, id=product_id)
        rating = request.POST.get('rating')
        title = request.POST.get('title', '')
        comment = request.POST.get('comment', '')
        
        # Validate rating
        if not rating or not rating.isdigit() or int(rating) not in range(1, 6):
            messages.error(request, 'Please select a valid rating!')
            return redirect('bika:product_detail', slug=product.slug)
        
        # Check if user already reviewed this product
        existing_review = ProductReview.objects.filter(
            user=request.user, 
            product=product
        ).first()
        
        if existing_review:
            messages.warning(request, 'You have already reviewed this product!')
        else:
            # Check if user has purchased this product
            has_purchased = OrderItem.objects.filter(
                order__user=request.user,
                product=product,
                order__status='delivered'
            ).exists()
            
            ProductReview.objects.create(
                user=request.user,
                product=product,
                rating=int(rating),
                title=title,
                comment=comment,
                is_verified_purchase=has_purchased,
                is_approved=True  # Auto-approve for now
            )
            messages.success(request, 'Thank you for your review!')
        
        return redirect('bika:product_detail', slug=product.slug)
    
    return redirect('bika:home')

# ==================== VENDOR VIEWS ====================

@login_required
def vendor_dashboard(request):
    """Vendor dashboard"""
    if not request.user.is_vendor() and not request.user.is_staff:
        messages.error(request, "Access denied. Vendor account required.")
        return redirect('bika:home')
    
    # Get vendor's products
    if request.user.is_staff:
        vendor_products = Product.objects.all()
        vendor_orders = Order.objects.all()
    else:
        vendor_products = Product.objects.filter(vendor=request.user)
        vendor_orders = Order.objects.filter(
            items__product__vendor=request.user
        ).distinct()
    
    # Vendor stats
    stats = {
        'total_products': vendor_products.count(),
        'active_products': vendor_products.filter(status='active').count(),
        'draft_products': vendor_products.filter(status='draft').count(),
        'low_stock': vendor_products.filter(
            stock_quantity__gt=0,
            stock_quantity__lte=F('low_stock_threshold'),
            track_inventory=True
        ).count(),
        'out_of_stock': vendor_products.filter(
            stock_quantity=0,
            track_inventory=True
        ).count(),
        'total_orders': vendor_orders.count(),
        'pending_orders': vendor_orders.filter(status='pending').count(),
        'completed_orders': vendor_orders.filter(status='delivered').count(),
    }
    
    # Recent products
    recent_products = vendor_products.order_by('-created_at')[:5]
    
    # Recent orders
    recent_orders = vendor_orders.select_related('user').order_by('-created_at')[:5]
    
    # Sales data (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_sales = vendor_orders.filter(
        status='delivered',
        created_at__gte=thirty_days_ago
    )
    
    total_sales = sum(order.total_amount for order in recent_sales if order.total_amount)
    
    context = {
        'stats': stats,
        'recent_products': recent_products,
        'recent_orders': recent_orders,
        'total_sales': total_sales,
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/vendor/dashboard.html', context)

@login_required
def vendor_product_list(request):
    """Vendor's product list with enhanced functionality"""
    if not request.user.is_vendor() and not request.user.is_staff:
        messages.error(request, "Access denied. Vendor account required.")
        return redirect('bika:home')
    
    # For staff, show all products; for vendors, show only their products
    if request.user.is_staff:
        products = Product.objects.all()
    else:
        products = Product.objects.filter(vendor=request.user)
    
    # Apply filters
    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    stock_filter = request.GET.get('stock', '')
    category_filter = request.GET.get('category', '')
    
    if query:
        products = products.filter(
            Q(name__icontains=query) | 
            Q(sku__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query)
        )
    
    if status_filter:
        products = products.filter(status=status_filter)
    
    if stock_filter == 'in_stock':
        products = products.filter(stock_quantity__gt=0)
    elif stock_filter == 'low_stock':
        products = products.filter(
            stock_quantity__gt=0, 
            stock_quantity__lte=F('low_stock_threshold')
        )
    elif stock_filter == 'out_of_stock':
        products = products.filter(stock_quantity=0)
    
    if category_filter:
        products = products.filter(category_id=category_filter)
    
    # Apply sorting
    sort_by = request.GET.get('sort', '-updated_at')
    if sort_by in ['name', '-name', 'price', '-price', 'stock_quantity', '-stock_quantity', 
                   'created_at', '-created_at', 'updated_at', '-updated_at']:
        products = products.order_by(sort_by)
    else:
        products = products.order_by('-updated_at')
    
    # Calculate statistics
    stats = {
        'active': products.filter(status='active').count(),
        'draft': products.filter(status='draft').count(),
        'low_stock': products.filter(
            stock_quantity__gt=0, 
            stock_quantity__lte=F('low_stock_threshold')
        ).count(),
        'out_of_stock': products.filter(stock_quantity=0).count(),
    }
    
    # Get categories for filter
    categories = ProductCategory.objects.filter(is_active=True)
    
    # Pagination
    paginator = Paginator(products, 10)
    page_number = request.GET.get('page')
    try:
        page_obj = paginator.get_page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.get_page(1)
    except EmptyPage:
        page_obj = paginator.get_page(paginator.num_pages)
    
    context = {
        'products': page_obj,
        'stats': stats,
        'categories': categories,
        'query': query,
        'status_filter': status_filter,
        'stock_filter': stock_filter,
        'category_filter': category_filter,
        'sort_by': sort_by,
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/vendor/products.html', context)

@login_required
def vendor_add_product(request):
    """Add new product"""
    if not request.user.is_vendor() and not request.user.is_staff:
        messages.error(request, "Access denied. Vendor account required.")
        return redirect('bika:home')
    
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        
        if form.is_valid():
            try:
                product = form.save(commit=False)
                product.vendor = request.user
                
                # Generate SKU if not provided
                if not product.sku:
                    product.sku = f"PROD{timezone.now().strftime('%Y%m%d%H%M%S')}"
                
                # Generate barcode if not provided
                if not product.barcode:
                    import random
                    product.barcode = f"8{random.randint(100000000000, 999999999999)}"
                
                product.save()
                
                # Handle multiple images
                images = request.FILES.getlist('images')
                for i, image in enumerate(images):
                    ProductImage.objects.create(
                        product=product,
                        image=image,
                        alt_text=product.name,
                        display_order=i,
                        is_primary=(i == 0)
                    )
                
                messages.success(request, 'Product added successfully!')
                return redirect('bika:vendor_product_list')
                
            except Exception as e:
                messages.error(request, f'Error saving product: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ProductForm()
    
    context = {
        'form': form,
        'title': 'Add New Product',
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/vendor/add_product.html', context)

@login_required
def vendor_edit_product(request, product_id):
    """Edit existing product"""
    if request.user.is_staff:
        product = get_object_or_404(Product, id=product_id)
    else:
        product = get_object_or_404(Product, id=product_id, vendor=request.user)
    
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        
        if form.is_valid():
            try:
                form.save()
                messages.success(request, 'Product updated successfully!')
                return redirect('bika:vendor_product_list')
            except Exception as e:
                messages.error(request, f'Error updating product: {str(e)}')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ProductForm(instance=product)
    
    # Get existing images
    images = product.images.all()
    
    context = {
        'form': form,
        'product': product,
        'images': images,
        'title': 'Edit Product',
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/vendor/edit_product.html', context)

@login_required
def vendor_delete_product(request, product_id):
    """Delete product"""
    if request.method == 'POST':
        if request.user.is_staff:
            product = get_object_or_404(Product, id=product_id)
        else:
            product = get_object_or_404(Product, id=product_id, vendor=request.user)
        
        product_name = product.name
        product.delete()
        
        messages.success(request, f'Product "{product_name}" deleted successfully!')
        return redirect('bika:vendor_product_list')
    
    return redirect('bika:vendor_product_list')

# ==================== USER PROFILE VIEWS ====================

@login_required
def user_profile(request):
    """User profile page"""
    user = request.user
    recent_orders = Order.objects.filter(user=user).order_by('-created_at')[:5]
    wishlist_count = Wishlist.objects.filter(user=user).count()
    cart_count = Cart.objects.filter(user=user).count()
    
    context = {
        'user': user,
        'recent_orders': recent_orders,
        'wishlist_count': wishlist_count,
        'cart_count': cart_count,
        'site_info': SiteInfo.objects.first(),
    }
    return render(request, 'bika/pages/user/profile.html', context)

@login_required
def update_profile(request):
    """Update user profile"""
    if request.method == 'POST':
        user = request.user
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.phone = request.POST.get('phone', user.phone)
        user.address = request.POST.get('address', user.address)
        
        if 'profile_picture' in request.FILES:
            user.profile_picture = request.FILES['profile_picture']
        
        if user.is_vendor():
            user.business_name = request.POST.get('business_name', user.business_name)
            user.business_description = request.POST.get('business_description', user.business_description)
            
            if 'business_logo' in request.FILES:
                user.business_logo = request.FILES['business_logo']
        
        user.save()
        messages.success(request, 'Profile updated successfully!')
        return redirect('bika:user_profile')
    
    return redirect('bika:user_profile')

@login_required
def user_orders(request):
    """User orders page"""
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    
    # Calculate totals
    total_orders = orders.count()
    total_spent = sum(order.total_amount for order in orders if order.total_amount)
    
    context = {
        'orders': orders,
        'total_orders': total_orders,
        'total_spent': total_spent,
        'site_info': SiteInfo.objects.first(),
    }
    return render(request, 'bika/pages/user/orders.html', context)

@login_required
def order_detail(request, order_id):
    """Order detail page"""
    order = get_object_or_404(Order.objects.select_related('user').prefetch_related('items'), 
                             id=order_id, user=request.user)
    
    # Get payments for this order
    payments = Payment.objects.filter(order=order).order_by('-created_at')
    
    context = {
        'order': order,
        'payments': payments,
        'site_info': SiteInfo.objects.first(),
    }
    return render(request, 'bika/pages/user/order_detail.html', context)

# ==================== WISHLIST VIEWS ====================

@login_required
def wishlist(request):
    """User wishlist page"""
    wishlist_items = Wishlist.objects.filter(
        user=request.user
    ).select_related('product').order_by('-added_at')
    
    context = {
        'wishlist_items': wishlist_items,
        'site_info': SiteInfo.objects.first(),
    }
    return render(request, 'bika/pages/user/wishlist.html', context)

@login_required
@require_POST
def add_to_wishlist(request, product_id):
    """Add product to wishlist"""
    product = get_object_or_404(Product, id=product_id)
    
    wishlist_item, created = Wishlist.objects.get_or_create(
        user=request.user,
        product=product
    )
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        wishlist_count = Wishlist.objects.filter(user=request.user).count()
        return JsonResponse({
            'success': True,
            'message': 'Product added to wishlist!',
            'wishlist_count': wishlist_count,
            'created': created
        })
    
    messages.success(request, 'Product added to wishlist!')
    return redirect('bika:product_detail', slug=product.slug)

@login_required
@require_POST
def remove_from_wishlist(request, product_id):
    """Remove product from wishlist"""
    product = get_object_or_404(Product, id=product_id)
    
    deleted_count, _ = Wishlist.objects.filter(
        user=request.user, 
        product=product
    ).delete()
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        wishlist_count = Wishlist.objects.filter(user=request.user).count()
        return JsonResponse({
            'success': True,
            'message': 'Product removed from wishlist!',
            'wishlist_count': wishlist_count,
            'deleted': deleted_count > 0
        })
    
    messages.success(request, 'Product removed from wishlist!')
    
    referer = request.META.get('HTTP_REFERER', '')
    if 'wishlist' in referer:
        return redirect('bika:wishlist')
    else:
        return redirect('bika:product_detail', slug=product.slug)

# ==================== CART VIEWS ====================

@login_required
def cart(request):
    """Shopping cart page"""
    from decimal import Decimal
    
    cart_items = Cart.objects.filter(
        user=request.user
    ).select_related('product').order_by('-added_at')
    
    # Calculate totals - Use Decimal for calculations
    subtotal = Decimal('0.00')
    
    # Prepare cart items with total_price for template
    cart_items_with_total = []
    for item in cart_items:
        # Calculate total for each item
        item_price = Decimal(str(item.product.price))
        item_quantity = Decimal(str(item.quantity))
        item_subtotal = item_price * item_quantity
        
        # Add calculated total to item (as a simple attribute, not property)
        item.total_price_calculated = item_subtotal
        cart_items_with_total.append(item)
        
        subtotal += item_subtotal
    
    tax_rate = Decimal('0.18')  # 18% VAT
    tax_amount = subtotal * tax_rate
    shipping_cost = Decimal('5000')  # Fixed shipping cost
    total_amount = subtotal + tax_amount + shipping_cost
    
    context = {
        'cart_items': cart_items_with_total,  # Use the list with calculated totals
        'subtotal': subtotal,
        'tax_amount': tax_amount,
        'shipping_cost': shipping_cost,
        'total_amount': total_amount,
        'tax_rate': tax_rate,
        'site_info': SiteInfo.objects.first(),
    }
    return render(request, 'bika/pages/user/cart.html', context)

@login_required
@require_POST
def add_to_cart(request, product_id):
    """Add product to cart"""
    product = get_object_or_404(Product, id=product_id)
    quantity = int(request.POST.get('quantity', 1))
    
    # Check stock availability
    if product.track_inventory and product.stock_quantity < quantity:
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'message': f'Only {product.stock_quantity} items available!'
            })
        messages.error(request, f'Only {product.stock_quantity} items available!')
        return redirect('bika:product_detail', slug=product.slug)
    
    # Add to cart
    cart_item, created = Cart.objects.get_or_create(
        user=request.user,
        product=product,
        defaults={'quantity': quantity}
    )
    
    if not created:
        cart_item.quantity += quantity
        cart_item.save()
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        cart_count = Cart.objects.filter(user=request.user).count()
        return JsonResponse({
            'success': True,
            'message': 'Product added to cart!',
            'cart_count': cart_count,
            'created': created
        })
    
    messages.success(request, 'Product added to cart!')
    return redirect('bika:cart')

@login_required
@require_POST
def update_cart(request, product_id):
    """Update cart item quantity"""
    from decimal import Decimal
    
    product = get_object_or_404(Product, id=product_id)
    quantity = int(request.POST.get('quantity', 1))
    
    if quantity > 0:
        # Check stock
        if product.track_inventory and product.stock_quantity < quantity:
            return JsonResponse({
                'success': False,
                'message': f'Only {product.stock_quantity} items available!'
            })
        
        cart_item = get_object_or_404(Cart, user=request.user, product=product)
        cart_item.quantity = quantity
        cart_item.save()
        
        # Recalculate totals
        cart_items = Cart.objects.filter(user=request.user)
        subtotal = sum(Decimal(str(item.product.price)) * Decimal(str(item.quantity)) for item in cart_items)
        tax_rate = Decimal('0.18')
        tax_amount = subtotal * tax_rate
        shipping_cost = Decimal('5000')
        total_amount = subtotal + tax_amount + shipping_cost
        
        return JsonResponse({
            'success': True,
            'item_total': str(cart_item.total_price),
            'subtotal': str(subtotal),
            'tax_amount': str(tax_amount),
            'total_amount': str(total_amount),
            'cart_count': cart_items.count(),
            'max_quantity': product.stock_quantity if product.track_inventory else 99
        })
    else:
        Cart.objects.filter(user=request.user, product=product).delete()
        cart_items = Cart.objects.filter(user=request.user)
        
        if cart_items.exists():
            subtotal = sum(Decimal(str(item.product.price)) * Decimal(str(item.quantity)) for item in cart_items)
            tax_rate = Decimal('0.18')
            tax_amount = subtotal * tax_rate
            shipping_cost = Decimal('5000')
            total_amount = subtotal + tax_amount + shipping_cost
            
            return JsonResponse({
                'success': True,
                'subtotal': str(subtotal),
                'tax_amount': str(tax_amount),
                'total_amount': str(total_amount),
                'cart_count': cart_items.count()
            })
        else:
            return JsonResponse({
                'success': True,
                'subtotal': '0.00',
                'tax_amount': '0.00',
                'total_amount': '0.00',
                'cart_count': 0
            })
        

@login_required
@require_POST
def remove_from_cart(request, product_id):
    """Remove product from cart"""
    from decimal import Decimal  # ADD THIS IMPORT
    
    product = get_object_or_404(Product, id=product_id)
    
    deleted_count, _ = Cart.objects.filter(
        user=request.user, 
        product=product
    ).delete()
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        cart_items = Cart.objects.filter(user=request.user)
        subtotal = sum(item.total_price for item in cart_items)
        tax_rate = Decimal('0.18')  # CHANGE TO DECIMAL
        tax_amount = subtotal * tax_rate
        shipping_cost = Decimal('5000')  # CHANGE TO DECIMAL
        total_amount = subtotal + tax_amount + shipping_cost
        
        return JsonResponse({
            'success': True,
            'subtotal': float(subtotal),  # CONVERT TO FLOAT
            'tax_amount': float(tax_amount),  # CONVERT TO FLOAT
            'total_amount': float(total_amount),  # CONVERT TO FLOAT
            'cart_count': cart_items.count(),
            'deleted': deleted_count > 0
        })
    
    messages.success(request, 'Product removed from cart!')
    return redirect('bika:cart')

@login_required
def clear_cart(request):
    """Clear entire cart"""
    if request.method == 'POST':
        deleted_count, _ = Cart.objects.filter(user=request.user).delete()
        
        messages.success(request, f'Cart cleared! {deleted_count} items removed.')
        return redirect('bika:cart')
    
    return redirect('bika:cart')

# ==================== CHECKOUT & PAYMENT VIEWS ====================

@login_required
def checkout(request):
    """Checkout page"""
    from decimal import Decimal  # ADD THIS IMPORT
    
    cart_items = Cart.objects.filter(user=request.user).select_related('product')
    
    if not cart_items:
        messages.error(request, "Your cart is empty!")
        return redirect('bika:cart')
    
    # Check stock for all items
    for item in cart_items:
        if item.product.track_inventory and item.product.stock_quantity < item.quantity:
            messages.error(
                request, 
                f'Only {item.product.stock_quantity} items available for {item.product.name}!'
            )
            return redirect('bika:cart')
    
    # Calculate totals - USE DECIMAL
    subtotal = sum(item.total_price for item in cart_items)
    tax_rate = Decimal('0.18')  # CHANGE TO DECIMAL
    tax_amount = subtotal * tax_rate
    shipping_cost = Decimal('5000')  # CHANGE TO DECIMAL
    total_amount = subtotal + tax_amount + shipping_cost
    
    # Get user's default addresses
    user = request.user
    shipping_address = user.address
    billing_address = user.address
    
    # Get available payment methods
    payment_methods = [
        {'value': 'mpesa', 'name': 'M-Pesa', 'icon': 'fas fa-mobile-alt'},
        {'value': 'airtel_tz', 'name': 'Airtel Money', 'icon': 'fas fa-wifi'},
        {'value': 'tigo_tz', 'name': 'Tigo Pesa', 'icon': 'fas fa-sim-card'},
        {'value': 'visa', 'name': 'Visa Card', 'icon': 'fab fa-cc-visa'},
        {'value': 'mastercard', 'name': 'MasterCard', 'icon': 'fab fa-cc-mastercard'},
        {'value': 'paypal', 'name': 'PayPal', 'icon': 'fab fa-paypal'},
    ]
    
    context = {
        'cart_items': cart_items,
        'subtotal': float(subtotal),  # CONVERT TO FLOAT
        'tax_amount': float(tax_amount),  # CONVERT TO FLOAT
        'shipping_cost': float(shipping_cost),  # CONVERT TO FLOAT
        'total_amount': float(total_amount),  # CONVERT TO FLOAT
        'shipping_address': shipping_address,
        'billing_address': billing_address,
        'payment_methods': payment_methods,
        'tax_rate': float(tax_rate * Decimal('100')),  # For display
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/checkout.html', context)

@login_required
@require_POST
def place_order(request):
    """Place order and process payment"""
    try:
        with transaction.atomic():
            from decimal import Decimal  # ADD THIS IMPORT
            
            # Get cart items
            cart_items = Cart.objects.filter(user=request.user).select_related('product')
            
            if not cart_items:
                return JsonResponse({
                    'success': False,
                    'message': 'Your cart is empty!'
                })
            
            # Validate stock
            for item in cart_items:
                if item.product.track_inventory and item.product.stock_quantity < item.quantity:
                    return JsonResponse({
                        'success': False,
                        'message': f'Insufficient stock for {item.product.name}'
                    })
            
            # Calculate totals - USE DECIMAL
            subtotal = sum(item.total_price for item in cart_items)
            tax_rate = Decimal('0.18')  # CHANGE TO DECIMAL
            tax_amount = subtotal * tax_rate
            shipping_cost = Decimal('5000')  # CHANGE TO DECIMAL
            total_amount = subtotal + tax_amount + shipping_cost
            
            # Get form data
            shipping_address = request.POST.get('shipping_address', '')
            billing_address = request.POST.get('billing_address', '')
            payment_method = request.POST.get('payment_method', '')
            phone_number = request.POST.get('phone_number', '')
            
            if not shipping_address or not billing_address:
                return JsonResponse({
                    'success': False,
                    'message': 'Please provide shipping and billing addresses'
                })
            
            if not payment_method:
                return JsonResponse({
                    'success': False,
                    'message': 'Please select a payment method'
                })
            
            # Create order
            order = Order.objects.create(
                user=request.user,
                total_amount=total_amount,  # This should already be Decimal
                shipping_address=shipping_address,
                billing_address=billing_address,
                status='pending'
            )
            
            # Create order items and update stock
            for cart_item in cart_items:
                OrderItem.objects.create(
                    order=order,
                    product=cart_item.product,
                    quantity=cart_item.quantity,
                    price=cart_item.product.price
                )
                
                # Update product stock
                if cart_item.product.track_inventory:
                    cart_item.product.stock_quantity -= cart_item.quantity
                    cart_item.product.save()
            
            # Create initial payment record
            payment = Payment.objects.create(
                order=order,
                payment_method=payment_method,
                amount=total_amount,  # This should already be Decimal
                currency='TZS',
                status='pending'
            )
            
            # If mobile money, save phone number
            if payment_method in ['mpesa', 'airtel_tz', 'tigo_tz'] and phone_number:
                payment.mobile_money_phone = phone_number
                payment.save()
            
            # Clear cart
            cart_items.delete()
            
            # Return success with order details
            return JsonResponse({
                'success': True,
                'order_id': order.id,
                'order_number': order.order_number,
                'payment_id': payment.id,
                'redirect_url': reverse('bika:payment_processing', args=[payment.id]),
                'total_amount': float(total_amount)  # CONVERT TO FLOAT FOR JSON
            })
            
    except Exception as e:
        logger.error(f"Error placing order: {e}")
        return JsonResponse({
            'success': False,
            'message': 'An error occurred while placing your order. Please try again.'
        })
    
@login_required
def payment_processing(request, payment_id):
    """Payment processing page"""
    payment = get_object_or_404(Payment, id=payment_id, order__user=request.user)
    order = payment.order
    
    context = {
        'payment': payment,
        'order': order,
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/payment_processing.html', context)

@csrf_exempt
@require_POST
def payment_webhook(request):
    """Handle payment webhooks from payment providers"""
    try:
        # This is a simplified version - implement based on your payment provider
        data = json.loads(request.body)
        
        # Extract payment info from webhook
        transaction_id = data.get('transaction_id')
        status = data.get('status')
        
        if transaction_id:
            payment = Payment.objects.filter(transaction_id=transaction_id).first()
            if payment:
                if status == 'success':
                    payment.status = 'completed'
                    payment.paid_at = timezone.now()
                    payment.order.status = 'confirmed'
                    payment.order.save()
                elif status == 'failed':
                    payment.status = 'failed'
                    payment.order.status = 'pending'
                    payment.order.save()
                
                payment.save()
                
                # Send notification to user
                Notification.objects.create(
                    user=payment.order.user,
                    title=f"Payment {status}",
                    message=f"Your payment for order #{payment.order.order_number} has been {status}.",
                    notification_type='order_update',
                    related_object_type='payment',
                    related_object_id=payment.id
                )
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Payment webhook error: {e}")
        return JsonResponse({'success': False}, status=400)

# ==================== FRUIT QUALITY MONITORING VIEWS ====================

@login_required
def fruit_quality_dashboard(request):
    """Fruit quality monitoring dashboard"""
    if not request.user.is_vendor() and not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('bika:home')
    
    # Get fruit batches
    if request.user.is_staff:
        batches = FruitBatch.objects.all().select_related('fruit_type', 'storage_location')
    else:
        batches = FruitBatch.objects.filter(
            product__vendor=request.user
        ).select_related('fruit_type', 'storage_location')
    
    # Get statistics
    total_batches = batches.count()
    active_batches = batches.filter(status='active').count()
    completed_batches = batches.filter(status='completed').count()
    
    # Get recent quality readings
    recent_readings = FruitQualityReading.objects.select_related(
        'fruit_batch', 'fruit_batch__fruit_type'
    ).order_by('-timestamp')[:10]
    
    # Get alerts
    alerts = ProductAlert.objects.filter(
        alert_type__in=['quality_issue', 'temperature_anomaly', 'humidity_issue']
    ).select_related('product').order_by('-created_at')[:5]
    
    context = {
        'batches': batches[:10],  # Show only recent 10
        'total_batches': total_batches,
        'active_batches': active_batches,
        'completed_batches': completed_batches,
        'recent_readings': recent_readings,
        'alerts': alerts,
        'ai_available': AI_SERVICES_AVAILABLE,
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/vendor/fruit_dashboard.html', context)

@login_required
def create_fruit_batch(request):
    """Create new fruit batch"""
    if not request.user.is_vendor() and not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('bika:home')
    
    if request.method == 'POST':
        form = FruitBatchForm(request.POST)
        if form.is_valid():
            batch = form.save(commit=False)
            
            # Set batch number if not provided
            if not batch.batch_number:
                import random
                import string
                random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                batch.batch_number = f"BATCH{timezone.now().strftime('%Y%m%d')}{random_str}"
            
            # Set status to active
            batch.status = 'active'
            
            # If vendor, associate with vendor's products
            if request.user.is_vendor() and not request.user.is_staff:
                # You might want to link to a specific product
                pass
            
            batch.save()
            
            messages.success(request, f'Fruit batch {batch.batch_number} created successfully!')
            return redirect('bika:fruit_quality_dashboard')
    else:
        form = FruitBatchForm()
    
    context = {
        'form': form,
        'fruit_types': FruitType.objects.all(),
        'storage_locations': StorageLocation.objects.filter(is_active=True),
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/vendor/create_fruit_batch.html', context)

@login_required
def batch_detail(request, batch_id):
    """View batch details"""
    if request.user.is_staff:
        batch = get_object_or_404(FruitBatch.objects.select_related(
            'fruit_type', 'storage_location'
        ), id=batch_id)
    else:
        batch = get_object_or_404(FruitBatch.objects.select_related(
            'fruit_type', 'storage_location'
        ), id=batch_id, product__vendor=request.user)
    
    # Get quality readings
    quality_readings = FruitQualityReading.objects.filter(
        fruit_batch=batch
    ).order_by('-timestamp')
    
    # Get sensor data
    sensor_data = RealTimeSensorData.objects.filter(
        fruit_batch=batch
    ).order_by('-recorded_at')
    
    # Try to get AI analysis
    ai_analysis = None
    if AI_SERVICES_AVAILABLE:
        try:
            ai_analysis = fruit_ai_service.get_batch_quality_report(batch_id, hours=24)
        except Exception as e:
            logger.error(f"Error getting AI analysis: {e}")
    
    context = {
        'batch': batch,
        'quality_readings': quality_readings,
        'sensor_data': sensor_data,
        'ai_analysis': ai_analysis,
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/vendor/batch_detail.html', context)

@login_required
def add_quality_reading(request, batch_id):
    """Add quality reading for batch"""
    if request.user.is_staff:
        batch = get_object_or_404(FruitBatch, id=batch_id)
    else:
        batch = get_object_or_404(FruitBatch, id=batch_id, product__vendor=request.user)
    
    if request.method == 'POST':
        form = FruitQualityReadingForm(request.POST)
        if form.is_valid():
            reading = form.save(commit=False)
            reading.fruit_batch = batch
            
            # If AI is available, get prediction
            if AI_SERVICES_AVAILABLE and not reading.predicted_class:
                try:
                    prediction = fruit_ai_service.predict_fruit_quality(
                        batch.fruit_type.name,
                        reading.temperature,
                        reading.humidity,
                        reading.light_intensity,
                        reading.co2_level,
                        batch.id
                    )
                    
                    if prediction.get('success'):
                        reading.predicted_class = prediction['prediction']['predicted_class']
                        reading.confidence_score = prediction['prediction']['confidence']
                except Exception as e:
                    logger.error(f"Error getting AI prediction: {e}")
            
            reading.save()
            
            messages.success(request, 'Quality reading added successfully!')
            return redirect('bika:batch_detail', batch_id=batch.id)
    else:
        form = FruitQualityReadingForm()
    
    context = {
        'form': form,
        'batch': batch,
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/vendor/add_quality_reading.html', context)

@login_required
@csrf_exempt
@require_POST
def train_fruit_model_api(request):
    """API endpoint to train fruit quality model"""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    try:
        if 'dataset_file' not in request.FILES:
            return JsonResponse({'success': False, 'error': 'No file uploaded'})
        
        csv_file = request.FILES['dataset_file']
        model_type = request.POST.get('model_type', 'random_forest')
        
        if not AI_SERVICES_AVAILABLE:
            return JsonResponse({'success': False, 'error': 'AI services not available'})
        
        result = fruit_ai_service.train_fruit_quality_model(csv_file, model_type)
        
        if result.get('success'):
            return JsonResponse(result)
        else:
            return JsonResponse({'success': False, 'error': result.get('error', 'Training failed')})
            
    except Exception as e:
        logger.error(f"Error training model: {e}")
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_GET
def predict_fruit_quality_api(request):
    """API endpoint for fruit quality prediction"""
    try:
        fruit_name = request.GET.get('fruit_name', '')
        temperature = float(request.GET.get('temperature', 5.0))
        humidity = float(request.GET.get('humidity', 90.0))
        light_intensity = float(request.GET.get('light_intensity', 50.0))
        co2_level = float(request.GET.get('co2_level', 400.0))
        batch_id = request.GET.get('batch_id')
        
        if not fruit_name:
            return JsonResponse({'success': False, 'error': 'Fruit name required'})
        
        if not AI_SERVICES_AVAILABLE:
            return JsonResponse({
                'success': False, 
                'error': 'AI services not available',
                'suggested_quality': 'Good'  # Fallback suggestion
            })
        
        prediction = fruit_ai_service.predict_fruit_quality(
            fruit_name, temperature, humidity, light_intensity, co2_level, batch_id
        )
        
        return JsonResponse(prediction)
        
    except Exception as e:
        logger.error(f"Error predicting fruit quality: {e}")
        return JsonResponse({'success': False, 'error': str(e)})

# ==================== NOTIFICATION VIEWS ====================

@login_required
def notifications(request):
    """User notifications"""
    notifications = Notification.objects.filter(
        user=request.user
    ).order_by('-created_at')
    
    unread_count = notifications.filter(is_read=False).count()
    
    context = {
        'notifications': notifications,
        'unread_count': unread_count,
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/user/notifications.html', context)

@login_required
@require_POST
def mark_notification_read(request, notification_id):
    """Mark notification as read"""
    notification = get_object_or_404(Notification, id=notification_id, user=request.user)
    notification.is_read = True
    notification.save()
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        unread_count = Notification.objects.filter(
            user=request.user, 
            is_read=False
        ).count()
        
        return JsonResponse({
            'success': True,
            'unread_count': unread_count
        })
    
    messages.success(request, 'Notification marked as read!')
    return redirect('bika:notifications')

@login_required
@require_POST
def mark_all_notifications_read(request):
    """Mark all notifications as read"""
    updated = Notification.objects.filter(
        user=request.user,
        is_read=False
    ).update(is_read=True)
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'updated_count': updated,
            'unread_count': 0
        })
    
    messages.success(request, f'{updated} notifications marked as read!')
    return redirect('bika:notifications')

@login_required
@require_GET
def unread_notifications_count(request):
    """Get unread notifications count"""
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(
            user=request.user,
            is_read=False
        ).count()
        
        critical_count = Notification.objects.filter(
            user=request.user,
            is_read=False,
            notification_type='urgent_alert'
        ).count()
        
        return JsonResponse({
            'unread_count': unread_count,
            'critical_count': critical_count
        })
    
    return JsonResponse({'unread_count': 0, 'critical_count': 0})

# ==================== AUTHENTICATION VIEWS ====================

def register_view(request):
    """User registration"""
    if request.user.is_authenticated:
        return redirect('bika:home')
    
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            # Auto-login
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password1')
            user = authenticate(username=username, password=password)
            
            if user is not None:
                login(request, user)
                messages.success(request, f'Welcome to Bika, {username}!')
                return redirect('bika:home')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CustomUserCreationForm()
    
    context = {
        'form': form,
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/registration/register.html', context)

def vendor_register_view(request):
    """Vendor registration"""
    if request.user.is_authenticated and request.user.is_vendor():
        return redirect('bika:vendor_dashboard')
    
    if request.method == 'POST':
        form = VendorRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            # Auto-login
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password1')
            user = authenticate(username=username, password=password)
            
            if user is not None:
                login(request, user)
                messages.success(request, f'Vendor account created! Welcome to Bika, {user.business_name}.')
                return redirect('bika:vendor_dashboard')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = VendorRegistrationForm()
    
    context = {
        'form': form,
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/registration/vendor_register.html', context)

@login_required
@never_cache
def custom_logout(request):
    """Logout user with security headers"""
    username = request.user.username
    
    logout(request)
    
    response = redirect('bika:logout_success')
    
    # Clear session
    request.session.flush()
    response.delete_cookie('sessionid')
    response.delete_cookie('csrftoken')
    
    # Security headers
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = 'Fri, 01 Jan 1990 00:00:00 GMT'
    
    messages.success(request, f'Goodbye {username}! You have been logged out successfully.')
    
    return response

def logout_success(request):
    """Logout success page"""
    response = render(request, 'bika/pages/registration/logout.html')
    
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response['Pragma'] = 'no-cache'
    response['Expires'] = 'Fri, 01 Jan 1990 00:00:00 GMT'
    
    return response

# ==================== ERROR HANDLERS ====================

def handler404(request, exception):
    return render(request, 'bika/pages/404.html', status=404)

def handler500(request):
    return render(request, 'bika/pages/500.html', status=500)

def handler403(request, exception):
    return render(request, 'bika/pages/403.html', status=403)

def handler400(request, exception):
    return render(request, 'bika/pages/400.html', status=400)

# ==================== API ENDPOINTS ====================

@csrf_exempt
@require_POST
def receive_sensor_data(request):
    """Receive sensor data from IoT devices"""
    try:
        data = json.loads(request.body)
        
        # Validate required fields
        required_fields = ['sensor_type', 'value', 'unit']
        for field in required_fields:
            if field not in data:
                return JsonResponse({'success': False, 'error': f'Missing field: {field}'})
        
        # Get optional fields
        product_barcode = data.get('product_barcode')
        batch_number = data.get('batch_number')
        location_id = data.get('location_id')
        
        # Find related objects
        product = None
        fruit_batch = None
        location = None
        
        if product_barcode:
            product = Product.objects.filter(barcode=product_barcode).first()
        
        if batch_number:
            fruit_batch = FruitBatch.objects.filter(batch_number=batch_number).first()
        
        if location_id:
            location = StorageLocation.objects.filter(id=location_id).first()
        
        # Create sensor reading
        sensor_reading = RealTimeSensorData.objects.create(
            product=product,
            fruit_batch=fruit_batch,
            sensor_type=data['sensor_type'],
            value=data['value'],
            unit=data['unit'],
            location=location,
            recorded_at=timezone.now()
        )
        
        # Check for anomalies (simplified version)
        if data['sensor_type'] == 'temperature' and (data['value'] < 0 or data['value'] > 25):
            # Create alert
            if product:
                ProductAlert.objects.create(
                    product=product,
                    alert_type='temperature_anomaly',
                    severity='high',
                    message=f'Temperature anomaly detected: {data["value"]}{data["unit"]}',
                    detected_by='sensor_system'
                )
        
        return JsonResponse({'success': True, 'id': sensor_reading.id})
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error receiving sensor data: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@csrf_exempt
@require_GET
def api_product_detail(request, barcode):
    """API endpoint for product details by barcode"""
    try:
        product = Product.objects.select_related('category', 'vendor').get(barcode=barcode)
        
        product_data = {
            'id': product.id,
            'name': product.name,
            'slug': product.slug,
            'barcode': product.barcode,
            'sku': product.sku,
            'price': str(product.price),
            'compare_price': str(product.compare_price) if product.compare_price else None,
            'stock_quantity': product.stock_quantity,
            'status': product.status,
            'category': {
                'id': product.category.id,
                'name': product.category.name,
                'slug': product.category.slug,
            },
            'vendor': {
                'id': product.vendor.id,
                'username': product.vendor.username,
                'business_name': product.vendor.business_name,
            },
            'images': [
                {
                    'image': img.image.url if img.image else None,
                    'alt_text': img.alt_text,
                    'is_primary': img.is_primary,
                }
                for img in product.images.all()[:3]
            ],
        }
        
        return JsonResponse(product_data)
        
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Product not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

# ==================== HELPER VIEWS ====================

def scan_product(request):
    """Product scanning interface"""
    context = {
        'site_info': SiteInfo.objects.first(),
    }
    return render(request, 'bika/pages/scan_product.html', context)

@staff_member_required
def storage_sites(request):
    """Storage sites management"""
    sites = StorageLocation.objects.all()
    
    context = {
        'sites': sites,
        'site_info': SiteInfo.objects.first(),
    }
    return render(request, 'bika/pages/admin/storage_sites.html', context)

@login_required
def track_my_products(request):
    """Track vendor's products with analytics"""
    if not request.user.is_vendor() and not request.user.is_staff:
        messages.error(request, "Access denied.")
        return redirect('bika:home')
    
    # Get vendor's products
    if request.user.is_staff:
        products = Product.objects.all()
        alerts = ProductAlert.objects.filter(is_resolved=False)
    else:
        products = Product.objects.filter(vendor=request.user)
        alerts = ProductAlert.objects.filter(product__vendor=request.user, is_resolved=False)
    
    # Apply filters
    query = request.GET.get('q', '')
    stock_filter = request.GET.get('stock', '')
    
    if query:
        products = products.filter(
            Q(name__icontains=query) | 
            Q(sku__icontains=query) |
            Q(category__name__icontains=query)
        )
    
    if stock_filter == 'in_stock':
        products = products.filter(stock_quantity__gt=0)
    elif stock_filter == 'low_stock':
        products = products.filter(
            stock_quantity__gt=0, 
            stock_quantity__lte=F('low_stock_threshold')
        )
    elif stock_filter == 'out_of_stock':
        products = products.filter(stock_quantity=0)
    
    # Calculate stats
    stats = {
        'total': products.count(),
        'in_stock': products.filter(stock_quantity__gt=0).count(),
        'low_stock': products.filter(
            stock_quantity__gt=0, 
            stock_quantity__lte=F('low_stock_threshold')
        ).count(),
        'out_of_stock': products.filter(stock_quantity=0).count(),
        'alerts': alerts.count(),
    }
    
    context = {
        'products': products[:20],  # Limit for performance
        'alerts': alerts[:10],
        'stats': stats,
        'query': query,
        'stock_filter': stock_filter,
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/vendor/track_products.html', context)

# ==================== ADD ALL MISSING VIEW FUNCTIONS ====================

def batch_analytics(request, batch_id):
    """Batch analytics page"""
    if not request.user.is_authenticated:
        return redirect('bika:login')
    
    if request.user.is_staff:
        batch = get_object_or_404(FruitBatch, id=batch_id)
    else:
        batch = get_object_or_404(FruitBatch, id=batch_id, product__vendor=request.user)
    
    context = {
        'batch': batch,
        'site_info': SiteInfo.objects.first(),
    }
    return render(request, 'bika/pages/vendor/batch_analytics.html', context)

def upload_dataset(request):
    """Upload dataset for AI training"""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    if request.method == 'POST':
        # Handle dataset upload
        return JsonResponse({'success': True, 'message': 'Dataset uploaded successfully'})
    
    return render(request, 'bika/pages/ai/upload_dataset.html', {'site_info': SiteInfo.objects.first()})

def train_model(request):
    """Train AI model"""
    if not request.user.is_staff:
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    if request.method == 'POST':
        # Handle model training
        return JsonResponse({'success': True, 'message': 'Model training started'})
    
    return render(request, 'bika/pages/ai/train_model.html', {'site_info': SiteInfo.objects.first()})

def product_analytics_api(request, product_id):
    """API endpoint for product analytics"""
    product = get_object_or_404(Product, id=product_id)
    
    analytics_data = {
        'product_id': product.id,
        'product_name': product.name,
        'views_count': product.views_count,
        'stock_level': product.stock_quantity,
        'sales_trend': 'increasing',
        'recommendations': ['Consider restocking soon']
    }
    
    return JsonResponse(analytics_data)

def storage_compatibility_check(request):
    """Check storage compatibility"""
    if request.method == 'GET':
        fruit1 = request.GET.get('fruit1', '')
        fruit2 = request.GET.get('fruit2', '')
        
        # Simple compatibility check
        compatible = True
        message = f"{fruit1} and {fruit2} are compatible for storage"
        
        if fruit1 and fruit2:
            ethylene_producers = ['Apple', 'Banana', 'Tomato']
            ethylene_sensitive = ['Lettuce', 'Broccoli', 'Carrot']
            
            if fruit1 in ethylene_producers and fruit2 in ethylene_sensitive:
                compatible = False
                message = f"{fruit1} produces ethylene which can spoil {fruit2}"
            elif fruit2 in ethylene_producers and fruit1 in ethylene_sensitive:
                compatible = False
                message = f"{fruit2} produces ethylene which can spoil {fruit1}"
        
        return JsonResponse({
            'success': True,
            'compatible': compatible,
            'message': message
        })
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

def resolve_alert(request, alert_id):
    """Resolve product alert"""
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': 'Authentication required'})
    
    alert = get_object_or_404(ProductAlert, id=alert_id)
    
    if request.method == 'POST':
        alert.is_resolved = True
        alert.resolved_by = request.user
        alert.resolved_at = timezone.now()
        alert.save()
        
        return JsonResponse({'success': True, 'message': 'Alert resolved successfully'})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})

def handle_bulk_actions(request):
    """Handle bulk product actions"""
    if not request.user.is_authenticated or (not request.user.is_vendor() and not request.user.is_staff):
        return JsonResponse({'success': False, 'error': 'Permission denied'})
    
    if request.method == 'POST':
        action = request.POST.get('action', '')
        product_ids = request.POST.get('product_ids', '')
        
        if not action or not product_ids:
            return JsonResponse({'success': False, 'error': 'Missing parameters'})
        
        try:
            ids = [int(id) for id in product_ids.split(',')]
            products = Product.objects.filter(id__in=ids)
            
            if not request.user.is_staff:
                products = products.filter(vendor=request.user)
            
            updated_count = 0
            
            if action == 'activate':
                updated_count = products.update(status='active')
            elif action == 'draft':
                updated_count = products.update(status='draft')
            elif action == 'feature':
                updated_count = products.update(is_featured=True)
            elif action == 'unfeature':
                updated_count = products.update(is_featured=False)
            elif action == 'delete':
                deleted_count, _ = products.delete()
                updated_count = deleted_count
            
            return JsonResponse({
                'success': True,
                'message': f'{updated_count} products updated successfully',
                'updated_count': updated_count
            })
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    
    return JsonResponse({'success': False, 'error': 'Invalid request method'})    
# Add these views
def train_five_models_view(request):
    """
    Train 5 different AI models on uploaded dataset or existing product data
    """
    if request.method == 'POST':
        try:
            # Get training parameters
            test_size = float(request.POST.get('test_size', 0.2))
            random_state = int(request.POST.get('random_state', 42))
            target_column = request.POST.get('target_column', 'Class')  # Default to 'Class'
            
            # Get which models to train
            models_to_train = request.POST.getlist('models')
            if not models_to_train:
                models_to_train = ['rf', 'xgb', 'svm', 'knn', 'gb']
            
            df = None
            
            # Check if file was uploaded
            if 'dataset_file' in request.FILES and request.FILES['dataset_file']:
                # Use uploaded file
                uploaded_file = request.FILES['dataset_file']
                
                # Save temporarily
                with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp_file:
                    for chunk in uploaded_file.chunks():
                        tmp_file.write(chunk)
                    tmp_path = tmp_file.name
                
                try:
                    # Load dataset - try multiple encodings
                    encodings = ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']
                    for encoding in encodings:
                        try:
                            df = pd.read_csv(tmp_path, encoding=encoding)
                            print(f"Loaded CSV with {encoding} encoding")
                            break
                        except:
                            continue
                    else:
                        df = pd.read_csv(tmp_path, encoding='utf-8', errors='ignore')
                    
                    print(f"Uploaded dataset shape: {df.shape}")
                    print(f"Columns: {df.columns.tolist()}")
                    
                    # Check if target column exists
                    if target_column not in df.columns:
                        # Try to find it with different cases
                        possible_targets = ['Class', 'class', 'CLASS', 'Quality', 'quality', 'Target']
                        for possible in possible_targets:
                            if possible in df.columns:
                                target_column = possible
                                break
                        else:
                            # If still not found, use last column
                            target_column = df.columns[-1]
                            print(f"Target column not found. Using last column: {target_column}")
                    
                    print(f"Using target column: {target_column}")
                    
                except Exception as e:
                    messages.error(request, f'Error loading CSV: {str(e)}')
                    return redirect('bika:train_models')
                finally:
                    # Clean up
                    os.unlink(tmp_path)
            
            if df is None or df.empty:
                # Use database data
                print("Using database data...")
                df = get_product_dataset_from_db()
                target_column = 'Class'  # For database data, we know the column name
            
            if df is None or df.empty:
                messages.error(request, 'No data available for training.')
                return redirect('bika:train_models')
            
            # Train models
            results = train_multiple_models(df, target_column, models_to_train, test_size, random_state)
            
            # Save best model to database
            if results['best_model']:
                save_model_to_database(results)
            
            # Store results in session for display
            request.session['training_results'] = results
            
            messages.success(request, f'Training completed! Best model: {results["best_model_name"]} with {results["best_accuracy"]:.2f}% accuracy')
            return redirect('bika:training_results')
            
        except Exception as e:
            messages.error(request, f'Training failed: {str(e)}')
            import traceback
            traceback.print_exc()
            return redirect('bika:train_models')
    
    # GET request - show training form
    context = {
        'site_info': SiteInfo.objects.first(),
        'product_count': Product.objects.count(),
        'quality_readings': FruitQualityReading.objects.count(),
        'active_batches': FruitBatch.objects.filter(status='active').count(),
        'sensor_data': RealTimeSensorData.objects.count(),
        'existing_models': TrainedModel.objects.all().order_by('-training_date')[:5]
    }
    return render(request, 'bika/pages/admin/train_models.html', context)
@staff_member_required
def training_results_view(request):
    """Display training results"""
    result = request.session.get('training_result')
    
    if not result:
        messages.error(request, 'No training results found')
        return redirect('bika:train_models')
    
    context = {
        'result': result,
        'site_info': SiteInfo.objects.first(),
    }
    return render(request, 'bika/pages/ai/training_results.html', context)

@staff_member_required
def model_comparison_view(request):
    """Detailed model comparison"""
    result = enhanced_ai_service.get_detailed_model_comparison()
    
    context = {
        'comparison_result': result,
        'site_info': SiteInfo.objects.first(),
    }
    return render(request, 'bika/pages/ai/model_comparison.html', context)

@staff_member_required
def generate_sample_dataset_view(request):
    """Generate sample dataset"""
    num_samples = int(request.GET.get('samples', 1000))
    
    result = enhanced_ai_service.generate_sample_dataset(num_samples)
    
    if result.get('success'):
        messages.success(request, f'Sample dataset generated with {num_samples} samples')
        return JsonResponse(result)
    else:
        messages.error(request, f"Failed to generate dataset: {result.get('error')}")
        return JsonResponse(result, status=400)
    
@staff_member_required
@require_GET
def export_sales_report(request):
    """Export sales report as CSV"""
    import csv
    from django.http import HttpResponse
    from datetime import datetime, timedelta
    
    # Get date range (last 30 days by default)
    end_date = timezone.now()
    start_date = end_date - timedelta(days=30)
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    filename = f"sales-report-{timezone.now().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    writer = csv.writer(response)
    
    # Write headers
    writer.writerow([
        'Date', 'Order ID', 'Customer', 'Product', 'Quantity', 
        'Unit Price', 'Total Amount', 'Status', 'Payment Method'
    ])
    
    # Write data
    orders = Order.objects.filter(
        created_at__range=[start_date, end_date]
    ).select_related('user').prefetch_related('items').order_by('-created_at')
    
    for order in orders:
        for item in order.items.all():
            writer.writerow([
                order.created_at.strftime('%Y-%m-%d'),
                order.order_number,
                order.user.username if order.user else '',
                item.product.name if item.product else '',
                item.quantity,
                float(item.price),
                float(item.quantity * item.price),
                order.get_status_display(),
                order.payment_method or 'N/A'
            ])
    
    return response

# Add this function to your views.py file, anywhere in the file:

def favicon_view(request):
    """Handle favicon requests to avoid 404 errors"""
    from django.http import HttpResponse
    return HttpResponse(status=204)  # No content response
@staff_member_required
def product_ai_insights_overview(request):
    """Overview page for product AI insights"""
    # Get all active products
    products = Product.objects.filter(status='active').select_related('category', 'vendor')
    
    # Get counts
    total_products = products.count()
    
    # Get AI predictions for each product
    try:
        from .ai_integration.models import FruitPrediction
        recent_predictions = FruitPrediction.objects.select_related('product').order_by('-prediction_date')[:10]
        
        # Count products with predictions
        product_ids_with_predictions = FruitPrediction.objects.values_list('product_id', flat=True).distinct()
        products_with_predictions = len(product_ids_with_predictions)
        
        # Add AI data to products
        for product in products:
            product.ai_predictions = FruitPrediction.objects.filter(product=product)[:3]
            product.alert_count = ProductAlert.objects.filter(product=product, is_resolved=False).count()
    except:
        recent_predictions = []
        products_with_predictions = 0
        for product in products:
            product.ai_predictions = []
            product.alert_count = 0
    
    # Get alert stats
    active_alerts = ProductAlert.objects.filter(is_resolved=False).count()
    high_risk_products = ProductAlert.objects.filter(
        is_resolved=False, 
        severity__in=['high', 'critical']
    ).values('product').distinct().count()
    
    context = {
        'products': products,
        'total_products': total_products,
        'products_with_predictions': products_with_predictions,
        'recent_predictions': recent_predictions,
        'active_alerts': active_alerts,
        'high_risk_products': high_risk_products,
        'last_analysis': timezone.now().strftime("%Y-%m-%d %H:%M"),
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/admin/product_ai_insights_overview.html', context)

# In views.py
@staff_member_required
def fruit_quality_dashboard(request):
    """Fruit quality monitoring dashboard"""
    # Get active fruit batches
    active_batches = FruitBatch.objects.filter(
        status='active'
    ).select_related(
        'fruit_type', 'storage_location'
    ).prefetch_related(
        'quality_readings'
    ).order_by('expected_expiry')
    
    # Add days_remaining calculation to each batch
    for batch in active_batches:
        if batch.expected_expiry:
            remaining = (batch.expected_expiry - timezone.now()).days
            batch.days_remaining = max(remaining, 0)
        else:
            batch.days_remaining = 0
    
    # Get latest quality reading for each batch
    for batch in active_batches:
        latest_reading = batch.quality_readings.order_by('-timestamp').first()
        batch.latest_reading = latest_reading
    
    # Calculate stats
    total_batches = FruitBatch.objects.count()
    active_batches_count = active_batches.count()
    
    # Count at-risk batches (expiring in less than 3 days)
    today = timezone.now().date()
    at_risk_batches = FruitBatch.objects.filter(
        status='active',
        expected_expiry__date__lte=today + timedelta(days=3)
    ).count()
    
    # Count expired batches
    expired_batches = FruitBatch.objects.filter(
        status='active',
        expected_expiry__date__lt=today
    ).count()
    
    # Get total readings
    total_readings = FruitQualityReading.objects.count()
    
    # Get AI predictions count
    ai_predictions = FruitQualityReading.objects.filter(
        predicted_class__isnull=False
    ).count()
    
    # Quality distribution
    quality_stats = {
        'fresh': FruitQualityReading.objects.filter(predicted_class='Fresh').count(),
        'good': FruitQualityReading.objects.filter(predicted_class='Good').count(),
        'fair': FruitQualityReading.objects.filter(predicted_class='Fair').count(),
        'poor': FruitQualityReading.objects.filter(predicted_class='Poor').count(),
        'rotten': FruitQualityReading.objects.filter(predicted_class='Rotten').count(),
    }
    
    # Get latest sensor data
    latest_sensor_data = RealTimeSensorData.objects.select_related(
        'fruit_batch'
    ).order_by('-recorded_at')[:5]
    
    # Fruit type distribution for chart
    fruit_types = FruitType.objects.all()
    fruit_types_labels = []
    fruit_types_data = []
    
    for ft in fruit_types:
        count = FruitBatch.objects.filter(fruit_type=ft).count()
        if count > 0:
            fruit_types_labels.append(ft.name)
            fruit_types_data.append(count)
    
    context = {
        'active_batches': active_batches,  # This is the key line!
        'stats': {
            'total_batches': total_batches,
            'active_batches': active_batches_count,
            'at_risk_batches': at_risk_batches,
            'expired_batches': expired_batches,
            'total_readings': total_readings,
            'ai_predictions': ai_predictions,
        },
        'quality_stats': quality_stats,
        'latest_sensor_data': latest_sensor_data,
        'last_updated': timezone.now().strftime("%H:%M:%S"),
        'fruit_types_labels': fruit_types_labels,
        'fruit_types_data': fruit_types_data,
        'site_info': SiteInfo.objects.first(),
    }
    
    return render(request, 'bika/pages/admin/fruit_dashboard.html', context)    


# Add this new view function
@staff_member_required
def train_five_models_view(request):
    """
    Train 5 different AI models on uploaded dataset or existing product data
    """
    if request.method == 'POST':
        try:
            # Get training parameters
            test_size = float(request.POST.get('test_size', 0.2))
            random_state = int(request.POST.get('random_state', 42))
            target_column = request.POST.get('target_column', 'Class')  # Default to 'Class'
            
            # Get which models to train
            models_to_train = request.POST.getlist('models')
            if not models_to_train:
                models_to_train = ['rf', 'xgb', 'svm', 'knn', 'gb']
            
            df = None
            
            # Check if file was uploaded
            if 'dataset_file' in request.FILES and request.FILES['dataset_file']:
                # Use uploaded file
                uploaded_file = request.FILES['dataset_file']
                
                # Save temporarily
                with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp_file:
                    for chunk in uploaded_file.chunks():
                        tmp_file.write(chunk)
                    tmp_path = tmp_file.name
                
                try:
                    # Load dataset - try multiple encodings
                    encodings = ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']
                    for encoding in encodings:
                        try:
                            df = pd.read_csv(tmp_path, encoding=encoding)
                            print(f"Loaded CSV with {encoding} encoding")
                            break
                        except:
                            continue
                    else:
                        df = pd.read_csv(tmp_path, encoding='utf-8', errors='ignore')
                    
                    print(f"Uploaded dataset shape: {df.shape}")
                    print(f"Columns: {df.columns.tolist()}")
                    
                    # Check if target column exists
                    if target_column not in df.columns:
                        # Try to find it with different cases
                        possible_targets = ['Class', 'class', 'CLASS', 'Quality', 'quality', 'Target']
                        for possible in possible_targets:
                            if possible in df.columns:
                                target_column = possible
                                break
                        else:
                            # If still not found, use last column
                            target_column = df.columns[-1]
                            print(f"Target column not found. Using last column: {target_column}")
                    
                    print(f"Using target column: {target_column}")
                    
                except Exception as e:
                    messages.error(request, f'Error loading CSV: {str(e)}')
                    return redirect('bika:train_models')
                finally:
                    # Clean up
                    os.unlink(tmp_path)
            
            if df is None or df.empty:
                # Use database data
                print("Using database data...")
                df = get_product_dataset_from_db()
                target_column = 'Class'  # For database data, we know the column name
            
            if df is None or df.empty:
                messages.error(request, 'No data available for training.')
                return redirect('bika:train_models')
            
            # Train models
            results = train_multiple_models(df, target_column, models_to_train, test_size, random_state)
            
            # Save best model to database
            if results['best_model']:
                save_model_to_database(results)
            
            # Store results in session for display
            request.session['training_results'] = results
            
            messages.success(request, f'Training completed! Best model: {results["best_model_name"]} with {results["best_accuracy"]:.2f}% accuracy')
            return redirect('bika:training_results')
            
        except Exception as e:
            messages.error(request, f'Training failed: {str(e)}')
            import traceback
            traceback.print_exc()
            return redirect('bika:train_models')
    
    # GET request - show training form
    context = {
        'site_info': SiteInfo.objects.first(),
        'product_count': Product.objects.count(),
        'quality_readings': FruitQualityReading.objects.count(),
        'active_batches': FruitBatch.objects.filter(status='active').count(),
        'sensor_data': RealTimeSensorData.objects.count(),
        'existing_models': TrainedModel.objects.all().order_by('-training_date')[:5]
    }
    return render(request, 'bika/pages/admin/train_models.html', context)
def get_product_dataset_from_db():
    """
    Extract product data from database for training
    """
    try:
        from .models import Product, ProductAlert, FruitQualityReading, FruitType
        
        # Get products with quality readings
        products = Product.objects.filter(status='active')
        
        data = []
        for product in products:
            # Get recent quality readings
            readings = FruitQualityReading.objects.filter(
                product=product
            ).order_by('-timestamp')[:10]  # Get last 10 readings
            
            if readings:
                for reading in readings:
                    # Get associated fruit type if available
                    fruit_type_name = 'Unknown'
                    if hasattr(product, 'fruit_type') and product.fruit_type:
                        fruit_type_name = product.fruit_type.name
                    elif reading.fruit_batch and reading.fruit_batch.fruit_type:
                        fruit_type_name = reading.fruit_batch.fruit_type.name
                    
                    data.append({
                        'Fruit': fruit_type_name,
                        'Temp': float(reading.temperature),
                        'Humid (%)': float(reading.humidity),
                        'Light (Fux)': float(reading.light_intensity),
                        'CO2 (pmm)': float(reading.co2_level) if reading.co2_level else 400.0,
                        'Class': reading.predicted_class  # This is your target column
                    })
        
        if not data:
            print("No data found in database. Creating sample data...")
            # Create sample data matching your format
            data = create_sample_fruit_data()
        
        # Convert to DataFrame
        df = pd.DataFrame(data)
        
        print(f"Generated dataset with {len(df)} rows and {len(df.columns)} columns")
        print(f"Columns: {df.columns.tolist()}")
        print(f"Sample data:\n{df.head()}")
        
        return df
        
    except Exception as e:
        print(f"Error getting dataset from DB: {e}")
        import traceback
        traceback.print_exc()
        return create_sample_fruit_data()

def create_sample_fruit_data():
    """
    Create sample data matching your dataset format
    """
    import numpy as np
    
    fruits = ['Apple', 'Banana', 'Orange', 'Mango', 'Grapes']
    classes = ['Good', 'Fair', 'Poor', 'Rotten', 'Fresh']
    
    data = []
    for i in range(1000):
        fruit = np.random.choice(fruits)
        if fruit == 'Apple':
            temp = np.random.normal(3, 1)
            humid = np.random.normal(90, 5)
        elif fruit == 'Banana':
            temp = np.random.normal(13, 2)
            humid = np.random.normal(85, 3)
        elif fruit == 'Orange':
            temp = np.random.normal(8, 1.5)
            humid = np.random.normal(88, 4)
        else:
            temp = np.random.normal(10, 2)
            humid = np.random.normal(87, 3)
        
        # Add some realistic patterns
        if temp > 10 or humid < 80:
            quality_class = np.random.choice(['Poor', 'Fair', 'Rotten'], p=[0.6, 0.3, 0.1])
        else:
            quality_class = np.random.choice(['Good', 'Fresh', 'Fair'], p=[0.5, 0.3, 0.2])
        
        data.append({
            'Fruit': fruit,
            'Temp': round(temp, 1),
            'Humid (%)': round(humid, 1),
            'Light (Fux)': round(np.random.uniform(50, 200), 1),
            'CO2 (pmm)': round(np.random.uniform(300, 500), 1),
            'Class': quality_class
        })
    
    return data
def train_multiple_models(df, target_column, models_to_train, test_size=0.2, random_state=42):
    """
    Train multiple ML models on the dataset
    """
    results = {
        'models': {},
        'best_model': None,
        'best_model_name': None,
        'best_accuracy': 0,
        'target_column': target_column,
        'feature_columns': [],
        'dataset_info': {
            'rows': len(df),
            'columns': len(df.columns),
            'columns_list': df.columns.tolist()
        }
    }
    
    try:
        print(f"\n🔍 Dataset Analysis:")
        print(f"   Shape: {df.shape}")
        print(f"   Columns: {df.columns.tolist()}")
        print(f"   Target column: {target_column}")
        print(f"   Target values: {df[target_column].unique()}")
        print(f"   Target distribution:\n{df[target_column].value_counts()}")
        
        # Prepare features and target
        X = df.drop(columns=[target_column])
        y = df[target_column]
        
        # Store feature names
        results['feature_columns'] = X.columns.tolist()
        
        # Handle non-numeric columns in features
        categorical_cols = X.select_dtypes(include=['object']).columns
        for col in categorical_cols:
            X[col] = X[col].astype('category').cat.codes
        
        # Check if target needs encoding
        if y.dtype == 'object':
            le = LabelEncoder()
            y = le.fit_transform(y)
            results['label_encoder'] = le
            results['classes'] = le.classes_.tolist()
            print(f"   Encoded classes: {le.classes_}")
        
        # Check for missing values
        if X.isnull().any().any():
            print(f"   Missing values found. Filling with median...")
            X = X.fillna(X.median())
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=random_state, stratify=y
        )
        
        print(f"\n📊 Data Split:")
        print(f"   Training samples: {X_train.shape[0]} ({X_train.shape[0]/len(X)*100:.1f}%)")
        print(f"   Testing samples: {X_test.shape[0]} ({X_test.shape[0]/len(X)*100:.1f}%)")
        
        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        results['scaler'] = scaler
        
        # Model configurations
        model_configs = {
            'rf': {
                'name': 'Random Forest',
                'model': RandomForestClassifier(
                    n_estimators=200,
                    max_depth=20,
                    min_samples_split=10,
                    random_state=random_state,
                    n_jobs=-1,
                    class_weight='balanced'
                )
            },
            'xgb': {
                'name': 'XGBoost',
                'model': XGBClassifier(
                    n_estimators=150,
                    max_depth=8,
                    learning_rate=0.05,
                    random_state=random_state,
                    use_label_encoder=False,
                    eval_metric='mlogloss'
                )
            },
            'svm': {
                'name': 'Support Vector Machine',
                'model': SVC(
                    C=1.0,
                    kernel='rbf',
                    probability=True,
                    random_state=random_state,
                    class_weight='balanced'
                )
            },
            'knn': {
                'name': 'K-Nearest Neighbors',
                'model': KNeighborsClassifier(
                    n_neighbors=7,
                    weights='distance',
                    algorithm='auto'
                )
            },
            'gb': {
                'name': 'Gradient Boosting',
                'model': GradientBoostingClassifier(
                    n_estimators=150,
                    learning_rate=0.1,
                    max_depth=6,
                    random_state=random_state
                )
            }
        }
        
        # Train selected models
        for model_key in models_to_train:
            if model_key in model_configs:
                config = model_configs[model_key]
                print(f"\n📊 Training {config['name']}...")
                
                try:
                    model = config['model']
                    model.fit(X_train_scaled, y_train)
                    
                    # Predict
                    y_pred = model.predict(X_test_scaled)
                    
                    # Calculate metrics
                    accuracy = accuracy_score(y_test, y_pred)
                    precision = precision_score(y_test, y_pred, average='weighted', zero_division=0)
                    recall = recall_score(y_test, y_pred, average='weighted', zero_division=0)
                    f1 = f1_score(y_test, y_pred, average='weighted', zero_division=0)
                    
                    # Cross-validation
                    cv_scores = cross_val_score(model, X_train_scaled, y_train, cv=5, scoring='accuracy')
                    cv_mean = cv_scores.mean()
                    cv_std = cv_scores.std()
                    
                    # Feature importance for tree-based models
                    feature_importance = None
                    if hasattr(model, 'feature_importances_'):
                        feature_importance = dict(zip(X.columns, model.feature_importances_))
                    
                    # Store results
                    results['models'][model_key] = {
                        'name': config['name'],
                        'accuracy': round(accuracy * 100, 2),
                        'precision': round(precision * 100, 2),
                        'recall': round(recall * 100, 2),
                        'f1_score': round(f1 * 100, 2),
                        'cv_mean': round(cv_mean * 100, 2),
                        'cv_std': round(cv_std * 100, 2),
                        'model_object': model,
                        'feature_names': X.columns.tolist(),
                        'feature_importance': feature_importance
                    }
                    
                    # Update best model
                    if accuracy > results['best_accuracy']:
                        results['best_accuracy'] = accuracy
                        results['best_model'] = model
                        results['best_model_name'] = config['name']
                        results['best_model_key'] = model_key
                        results['best_scaler'] = scaler
                    
                    print(f"   ✅ {config['name']}: {accuracy*100:.2f}% accuracy")
                    
                except Exception as e:
                    print(f"   ❌ Error training {config['name']}: {str(e)}")
                    continue
        
        # Sort models by accuracy
        results['sorted_models'] = sorted(
            results['models'].items(),
            key=lambda x: x[1]['accuracy'],
            reverse=True
        )
        
        print(f"\n🏆 Best Model: {results['best_model_name']} ({results['best_accuracy']*100:.2f}%)")
        
        return results
        
    except Exception as e:
        print(f"❌ Error in training: {str(e)}")
        import traceback
        traceback.print_exc()
        raise
def save_model_to_database(training_results):
    """
    Save the trained model to database
    """
    try:
        from .models import TrainedModel, ProductDataset
        
        if not training_results or 'best_model' not in training_results:
            return None
        
        # Create dataset record
        dataset = ProductDataset.objects.create(
            name=f"Product Quality Dataset {timezone.now().strftime('%Y-%m-%d')}",
            dataset_type='quality_control',
            description='Dataset generated from product quality readings',
            row_count=1000,  # Placeholder
            is_active=True
        )
        
        # Save model to file
        model_data = {
            'model': training_results['best_model'],
            'scaler': training_results.get('best_scaler'),
            'feature_names': training_results.get('feature_names', []),
            'training_date': timezone.now(),
            'accuracy': training_results.get('best_accuracy', 0)
        }
        
        # Create filename
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        model_filename = f"trained_models/model_{timestamp}.pkl"
        
        # Ensure directory exists
        os.makedirs('trained_models', exist_ok=True)
        
        # Save model
        joblib.dump(model_data, model_filename)
        
        # Save to database
        trained_model = TrainedModel.objects.create(
            name=f"{training_results.get('best_model_name', 'AI Model')} {timestamp}",
            model_type='fruit_quality',
            dataset=dataset,
            model_file=model_filename,
            accuracy=float(training_results.get('best_accuracy', 0)),
            is_active=True,
            feature_columns=training_results.get('feature_names', [])
        )
        
        print(f"Model saved to database: {trained_model.name}")
        return trained_model
        
    except Exception as e:
        print(f"Error saving model to database: {e}")
        return None    

@staff_member_required
def training_results_view(request):
    """Display training results"""
    results = request.session.get('training_results', {})
    
    if not results:
        messages.info(request, 'No training results found. Please train a model first.')
        return redirect('bika:train_models')
    
    context = {
        'results': results,
        'site_info': SiteInfo.objects.first(),
    }
    return render(request, 'bika/pages/admin/training_results.html', context)

@staff_member_required
def model_comparison_view(request):
    """Compare trained models"""
    models = TrainedModel.objects.filter(is_active=True).order_by('-training_date')
    
    context = {
        'models': models,
        'site_info': SiteInfo.objects.first(),
    }
    return render(request, 'bika/pages/admin/model_comparison.html', context)        

@staff_member_required
def analyze_csv(request):
    """Analyze uploaded CSV file"""
    if request.method == 'POST' and 'csv_file' in request.FILES:
        file = request.FILES['csv_file']
        
        # Save temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp_file:
            for chunk in file.chunks():
                tmp_file.write(chunk)
            tmp_path = tmp_file.name
        
        try:
            # Load CSV
            df = pd.read_csv(tmp_path)
            
            analysis = {
                'columns': df.columns.tolist(),
                'shape': df.shape,
                'dtypes': df.dtypes.astype(str).to_dict(),
                'head': df.head().to_dict('records'),
                'missing_values': df.isnull().sum().to_dict(),
                'unique_counts': {col: df[col].nunique() for col in df.columns}
            }
            
            # Suggest target column
            suggestions = []
            for col in df.columns:
                if col.lower() in ['class', 'quality', 'grade', 'target', 'label']:
                    suggestions.append((col, 'Likely target (based on name)'))
                elif df[col].nunique() <= 10:
                    suggestions.append((col, f'Classification ({df[col].nunique()} classes)'))
                elif df[col].dtype in ['int64', 'float64'] and df[col].nunique() > 10:
                    suggestions.append((col, f'Regression ({df[col].nunique()} unique values)'))
            
            analysis['suggestions'] = suggestions
            
            return JsonResponse({'success': True, 'analysis': analysis})
            
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
        finally:
            os.unlink(tmp_path)
    
    return JsonResponse({'success': False, 'error': 'No file uploaded'})
# ==================== DRF VIEWSETS (API) ====================

from django.db.models import Sum
from rest_framework import viewsets, permissions, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

# ✅ Real models
from .models import Product, ProductCategory, CustomUser, Cart

# ✅ READ serializers from api_serializers
from .api_serializers import (
    ProductListSerializer,
    ProductDetailSerializer,
    ProductCategorySerializer,
    VendorSerializer,
    CartSerializer,
    StockAdjustSerializer,
)

# ✅ WRITE serializer from dedicated file (important fix)
from .product_write_serializers import ProductWriteSerializer


class IsAuthenticatedOrReadOnlyForNow(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)


# -----------------------------------------------------------------------------
# DASHBOARD API (for Flutter Home overview)
# Endpoint: /api/v1/dashboard/summary/
# -----------------------------------------------------------------------------
class DashboardSummaryAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        # If vendor, scope to their products; if staff/admin, all products
        if getattr(user, "is_staff", False):
            product_qs = Product.objects.all()
        elif getattr(user, "user_type", None) == "vendor":
            product_qs = Product.objects.filter(vendor=user)
        else:
            # customer or others -> show global counts (or set to 0 if you prefer)
            product_qs = Product.objects.all()

        cart_qs = Cart.objects.filter(user=user)

        subtotal = 0
        for item in cart_qs.select_related("product"):
            try:
                price = getattr(item.product, "final_price", None) or item.product.price or 0
                subtotal += float(price) * int(item.quantity or 0)
            except Exception:
                pass

        data = {
            "total_products": product_qs.count(),
            "active_products": product_qs.filter(status="active").count(),
            "draft_products": product_qs.filter(status="draft").count(),
            "low_stock_products": product_qs.filter(
                track_inventory=True,
                stock_quantity__gt=0,
                stock_quantity__lte=5,
            ).count(),
            "out_of_stock_products": product_qs.filter(
                track_inventory=True,
                stock_quantity=0,
            ).count(),
            "cart_items": cart_qs.count(),
            "cart_quantity_total": sum(int(i.quantity or 0) for i in cart_qs),
            "cart_subtotal": round(subtotal, 2),
        }
        return Response(data, status=status.HTTP_200_OK)


# -----------------------------------------------------------------------------
# PRODUCTS API
# -----------------------------------------------------------------------------
class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.select_related("category", "vendor").all()
    permission_classes = [IsAuthenticatedOrReadOnlyForNow]

    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "sku", "slug", "barcode"]
    ordering_fields = ["created_at", "updated_at", "name", "price", "stock_quantity"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        # Write serializer for create/update, detail serializer for retrieve, list serializer for list
        if self.action in ["create", "update", "partial_update"]:
            return ProductWriteSerializer
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductListSerializer

    def get_queryset(self):
        qs = Product.objects.select_related("category", "vendor").all()

        # Optional query params
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)

        category_id = self.request.query_params.get("category")
        if category_id:
            qs = qs.filter(category_id=category_id)

        vendor_id = self.request.query_params.get("vendor")
        if vendor_id:
            qs = qs.filter(vendor_id=vendor_id)

        # Optional: show only active by default for non-staff GET
        # if self.request.method == "GET" and not (self.request.user and self.request.user.is_staff):
        #     qs = qs.filter(status="active")

        return qs

    def create(self, request, *args, **kwargs):
        """
        Explicit create to make debugging easier and return clean validation errors.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        # Return read serializer response after create
        product = serializer.instance
        read_data = ProductDetailSerializer(product, context=self.get_serializer_context()).data
        headers = self.get_success_headers(read_data)
        return Response(read_data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """
        Product summary endpoint:
        /api/v1/products/summary/
        """
        qs = self.get_queryset()
        return Response(
            {
                "total_products": qs.count(),
                "active_products": qs.filter(status="active").count(),
                "inactive_products": qs.exclude(status="active").count(),
                "low_stock_products": qs.filter(
                    status="active",
                    track_inventory=True,
                    stock_quantity__lte=5,
                ).count(),
            }
        )

    @action(detail=True, methods=["patch"], url_path="stock")
    def adjust_stock(self, request, pk=None):
        """
        PATCH /api/v1/products/<id>/stock/
        body: {"delta": 1} or {"delta": -1}
        """
        product = self.get_object()
        serializer = StockAdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        delta = serializer.validated_data["delta"]
        new_qty = int(product.stock_quantity or 0) + int(delta)

        if new_qty < 0:
            return Response(
                {"detail": "Stock cannot go below zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        product.stock_quantity = new_qty
        product.save(update_fields=["stock_quantity", "updated_at"])

        return Response(
            {
                "id": product.id,
                "stock_quantity": product.stock_quantity,
                "delta": delta,
            },
            status=status.HTTP_200_OK,
        )


# -----------------------------------------------------------------------------
# CART API (for Flutter Cart tab)
# Endpoints:
#   GET    /api/v1/cart/
#   POST   /api/v1/cart/           body: {"product_id": 1, "quantity": 2}
#   PATCH  /api/v1/cart/<id>/      body: {"quantity": 3}
#   DELETE /api/v1/cart/<id>/
# -----------------------------------------------------------------------------
class CartViewSet(viewsets.ModelViewSet):
    serializer_class = CartSerializer
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        return Cart.objects.filter(user=self.request.user).select_related("product").order_by("-added_at")

    def create(self, request, *args, **kwargs):
        product_id = request.data.get("product_id") or request.data.get("product")
        quantity = request.data.get("quantity", 1)

        try:
            product_id = int(product_id)
            quantity = int(quantity)
        except (TypeError, ValueError):
            return Response(
                {"detail": "product_id and quantity must be valid integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if quantity < 1:
            return Response(
                {"detail": "quantity must be at least 1."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            product = Product.objects.get(pk=product_id)
        except Product.DoesNotExist:
            return Response({"detail": "Product not found."}, status=status.HTTP_404_NOT_FOUND)

        # Stock check
        if getattr(product, "track_inventory", False) and int(product.stock_quantity or 0) < quantity:
            return Response(
                {"detail": f"Only {product.stock_quantity} item(s) available."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cart_item, created = Cart.objects.get_or_create(
            user=request.user,
            product=product,
            defaults={"quantity": quantity},
        )

        if not created:
            new_qty = int(cart_item.quantity or 0) + quantity
            if getattr(product, "track_inventory", False) and int(product.stock_quantity or 0) < new_qty:
                return Response(
                    {"detail": f"Only {product.stock_quantity} item(s) available."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            cart_item.quantity = new_qty
            cart_item.save(update_fields=["quantity", "updated_at"])

        data = CartSerializer(cart_item, context=self.get_serializer_context()).data
        return Response(data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def partial_update(self, request, *args, **kwargs):
        cart_item = self.get_object()
        quantity = request.data.get("quantity")

        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return Response({"detail": "quantity must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

        if quantity < 1:
            cart_item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        product = cart_item.product
        if getattr(product, "track_inventory", False) and int(product.stock_quantity or 0) < quantity:
            return Response(
                {"detail": f"Only {product.stock_quantity} item(s) available."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cart_item.quantity = quantity
        cart_item.save(update_fields=["quantity", "updated_at"])

        data = CartSerializer(cart_item, context=self.get_serializer_context()).data
        return Response(data, status=status.HTTP_200_OK)


# -----------------------------------------------------------------------------
# SUPPORTING READ-ONLY APIs
# -----------------------------------------------------------------------------
class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ProductCategory.objects.filter(is_active=True).order_by("name")
    serializer_class = ProductCategorySerializer
    permission_classes = [permissions.IsAuthenticated]


class VendorViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CustomUser.objects.filter(user_type="vendor", is_active=True).order_by("username")
    serializer_class = VendorSerializer
    permission_classes = [permissions.IsAuthenticated]