from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count
import django
import sys
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.views.generic import ListView, DetailView, TemplateView

from .models import SiteInfo, Service, Testimonial, ContactMessage, FAQ
from .forms import ContactForm, NewsletterForm
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.conf import settings
from django.views.generic import ListView, DetailView, TemplateView
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
import django
import sys

# Import ALL your models
from .models import (
    SiteInfo, Service, Testimonial, ContactMessage, FAQ,
    CustomUser, Product, ProductCategory, ProductImage, ProductReview
)
from .forms import (
    ContactForm, NewsletterForm, CustomUserCreationForm, 
    VendorRegistrationForm, CustomerRegistrationForm, ProductForm
)
class HomeView(TemplateView):
    template_name = 'bika/home.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # Existing services and testimonials
        context['featured_services'] = Service.objects.filter(is_active=True)[:6]
        context['featured_testimonials'] = Testimonial.objects.filter(
            is_active=True, 
            is_featured=True
        )[:3]
        context['faqs'] = FAQ.objects.filter(is_active=True)[:5]
        
        # Add featured products with error handling
        try:
            # Check if Product model exists and has data
            featured_products = Product.objects.filter(
                status='active',
                is_featured=True
            ).select_related('category', 'vendor')[:8]
            
            # Add primary images to products
            for product in featured_products:
                try:
                    product.primary_image = product.images.filter(is_primary=True).first()
                    if not product.primary_image:
                        product.primary_image = product.images.first()
                except Exception:
                    product.primary_image = None
            
            context['featured_products'] = featured_products
            
        except Exception as e:
            # If there's any error (model doesn't exist, no data, etc.)
            print(f"Error loading featured products: {e}")
            context['featured_products'] = []
        
        # Add site info if available
        try:
            context['site_info'] = SiteInfo.objects.first()
        except Exception:
            context['site_info'] = None
        
        return context


def about_view(request):
    services = Service.objects.filter(is_active=True)
    testimonials = Testimonial.objects.filter(is_active=True)[:4]
    
    context = {
        'services': services,
        'testimonials': testimonials,
    }
    return render(request, 'bika/pages/about.html', context)

def services_view(request):
    services = Service.objects.filter(is_active=True)
    return render(request, 'bika/pages/services.html', {'services': services})

class ServiceDetailView(DetailView):
    model = Service
    template_name = 'bika/pages/service_detail.html'
    context_object_name = 'service'
    slug_field = 'slug'
    slug_url_kwarg = 'slug'

def contact_view(request):
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
            
            # Send email notification (optional)
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
                # Log error but don't show to user
                pass
            
            messages.success(
                request, 
                'Thank you for your message! We will get back to you soon.'
            )
            return redirect('bika:contact')
    else:
        form = ContactForm()
    
    return render(request, 'bika/pages/contact.html', {'form': form})

def faq_view(request):
    faqs = FAQ.objects.filter(is_active=True)
    return render(request, 'bika/pages/faq.html', {'faqs': faqs})

def newsletter_subscribe(request):
    if request.method == 'POST' and request.headers.get('x-requested-with') == 'XMLHttpRequest':
        form = NewsletterForm(request.POST)
        if form.is_valid():
            # Here you would typically save to database
            # For now, we'll just return success
            email = form.cleaned_data['email']
            return JsonResponse({
                'success': True,
                'message': 'Thank you for subscribing to our newsletter!'
            })
        else:
            return JsonResponse({
                'success': False,
                'message': 'Please enter a valid email address.'
            })
    return JsonResponse({'success': False, 'message': 'Invalid request'})

def handler404(request, exception):
    return render(request, 'bika/pages/404.html', status=404)

def handler500(request):
    return render(request, 'bika/pages/500.html', status=500)


def custom_404(request, exception):
    return render(request, 'bika/pages/404.html', status=404)

def custom_500(request):
    return render(request, 'bika/pages/500.html', status=500)

# Optional: Test view to trigger 500 error (remove in production)
def test_500(request):
    # This will trigger a 500 error for testing
    raise Exception("This is a test 500 error")



def admin_dashboard(request):
    """Custom admin dashboard"""
    if not request.user.is_staff:
        return redirect('admin:login')
    
    # Get current date and time
    now = timezone.now()
    last_week = now - timedelta(days=7)
    
    # Statistics
    total_services = Service.objects.count()
    total_testimonials = Testimonial.objects.count()
    total_messages = ContactMessage.objects.count()
    new_messages = ContactMessage.objects.filter(status='new').count()
    
    # Additional stats
    active_services_count = Service.objects.filter(is_active=True).count()
    featured_testimonials_count = Testimonial.objects.filter(is_featured=True, is_active=True).count()
    active_faqs_count = FAQ.objects.filter(is_active=True).count()
    
    # Recent activity
    recent_messages = ContactMessage.objects.all().order_by('-submitted_at')[:5]
    
    # System information
    import django
    import sys
    from django.conf import settings
    
    context = {
        # Basic stats
        'total_services': total_services,
        'total_testimonials': total_testimonials,
        'total_messages': total_messages,
        'new_messages': new_messages,
        
        # Additional stats
        'active_services_count': active_services_count,
        'featured_testimonials_count': featured_testimonials_count,
        'active_faqs_count': active_faqs_count,
        
        # Recent activity
        'recent_messages': recent_messages,
        
        # System info
        'django_version': django.get_version(),
        'python_version': sys.version.split()[0],
        'debug': settings.DEBUG,
    }
    
    return render(request, 'admin/dashboard.html', context)
def product_list_view(request):
    """Display all active products with filtering and pagination"""
    products = Product.objects.filter(status='active').select_related('category', 'vendor')
    
    # Get filter parameters
    category_slug = request.GET.get('category')
    query = request.GET.get('q', '')
    sort_by = request.GET.get('sort', 'newest')
    
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
            Q(category__name__icontains=query)
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
    paginator = Paginator(products, 12)  # 12 products per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get categories for sidebar
    categories = ProductCategory.objects.filter(is_active=True).annotate(
        product_count=Count('products', filter=Q(products__status='active'))
    )
    
    # Count active vendors
    active_vendors = CustomUser.objects.filter(
        user_type='vendor', 
        product__status='active'
    ).distinct().count()
    
    context = {
        'products': page_obj,
        'categories': categories,
        'current_category': current_category,
        'query': query,
        'total_products': products.count(),
        'active_vendors': active_vendors,
    }
    return render(request, 'bika/pages/products.html', context)
    
def product_detail_view(request, slug):
    """Display single product details"""
    product = get_object_or_404(Product, slug=slug, status='active')
    
    context = {
        'product': product,
        'related_products': product.get_related_products(),
    }
    return render(request, 'bika/pages/product_detail.html', context)

def products_by_category_view(request, category_slug):
    """Display products by category"""
    category = get_object_or_404(ProductCategory, slug=category_slug, is_active=True)
    products = Product.objects.filter(category=category, status='active')
    
    context = {
        'category': category,
        'products': products,
        'categories': ProductCategory.objects.filter(is_active=True),
    }
    return render(request, 'bika/pages/products_by_category.html', context)

def product_search_view(request):
    """Handle product search"""
    query = request.GET.get('q', '')
    products = Product.objects.filter(status='active')
    
    if query:
        products = products.filter(
            Q(name__icontains=query) | 
            Q(description__icontains=query) |
            Q(short_description__icontains=query) |
            Q(tags__icontains=query)
        )
    
    context = {
        'products': products,
        'query': query,
        'categories': ProductCategory.objects.filter(is_active=True),
    }
    return render(request, 'bika/pages/product_search.html', context)

def vendor_dashboard(request):
    """Vendor dashboard"""
    if not request.user.is_authenticated or not request.user.is_vendor():
        messages.error(request, "Access denied. Vendor account required.")
        return redirect('bika:home')
    
    # Get vendor's products
    vendor_products = Product.objects.filter(vendor=request.user)
    
    context = {
        'total_products': vendor_products.count(),
        'active_products': vendor_products.filter(status='active').count(),
        'draft_products': vendor_products.filter(status='draft').count(),
        'recent_products': vendor_products.order_by('-created_at')[:5],
    }
    return render(request, 'bika/pages/vendor_dashboard.html', context)

def vendor_product_list(request):
    """Vendor's product list"""
    if not request.user.is_authenticated or not request.user.is_vendor():
        messages.error(request, "Access denied. Vendor account required.")
        return redirect('bika:home')
    
    products = Product.objects.filter(vendor=request.user)
    
    context = {
        'products': products,
    }
    return render(request, 'bika/pages/vendor_products.html', context)

def vendor_add_product(request):
    """Vendor add product form"""
    if not request.user.is_authenticated or not request.user.is_vendor():
        messages.error(request, "Access denied. Vendor account required.")
        return redirect('bika:dashboard')
    
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.vendor = request.user
            product.save()
            messages.success(request, f"Product '{product.name}' added successfully!")
            return redirect('bika:vendor_product_list')
    else:
        form = ProductForm()
    
    context = {
        'form': form,
    }
    return render(request, 'bika/pages/vendor_add_product.html', context)

def vendor_register_view(request):
    """Special vendor registration"""
    # Only redirect logged-in users who are ALREADY vendors
    if request.user.is_authenticated and request.user.is_vendor():
        messages.info(request, "You are already a registered vendor!")
        return redirect('bika:dashboard')
    
    # Show warning for logged-in customers but still show the form
    if request.user.is_authenticated and not request.user.is_vendor():
        messages.warning(request, "You already have a customer account. Please contact support to convert to vendor.")
    
    if request.method == 'POST':
        form = VendorRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            # Auto-login after registration
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password1')
            user = authenticate(username=username, password=password)
            
            if user is not None:
                login(request, user)
                messages.success(request, f"Vendor account created successfully! Welcome to Bika, {user.business_name}.")
                return redirect('bika:dashboard')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = VendorRegistrationForm()
    
    return render(request, 'bika/pages/registration/vendor_register.html', {'form': form})

def register_view(request):
    """User registration view"""
    if request.user.is_authenticated:
        messages.info(request, "You are already logged in!")
        return redirect('bika:home')
    
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            # Auto-login after registration
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password1')
            user = authenticate(username=username, password=password)
            
            if user is not None:
                login(request, user)
                messages.success(request, f'Account created successfully! Welcome to Bika, {username}.')
                return redirect('bika:home')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CustomUserCreationForm()
    
    return render(request, 'bika/pages/registration/register.html', {'form': form})
