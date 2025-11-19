from .models import SiteInfo, Service, Cart

def site_info(request):
    """Add site information and other context to all templates"""
    context = {}
    
    # Site Information
    try:
        site_info_obj = SiteInfo.objects.first()
        if not site_info_obj:
            # Create default site info if it doesn't exist
            site_info_obj = SiteInfo.objects.create(
                name="Bika",
                tagline="Your Success Is Our Business",
                description="Bika provides exceptional services to help your business grow.",
                email="contact@bika.com"
            )
        context['site_info'] = site_info_obj
    except Exception as e:
        print(f"SiteInfo error: {e}")
        context['site_info'] = None
    
    # Featured Services (for navigation dropdown)
    try:
        context['featured_services'] = Service.objects.filter(is_active=True)[:6]
    except Exception as e:
        print(f"Services error: {e}")
        context['featured_services'] = []
    
    # Cart Count (for header badge)
    try:
        if request.user.is_authenticated:
            context['cart_count'] = Cart.objects.filter(user=request.user).count()
        else:
            context['cart_count'] = 0
    except Exception as e:
        print(f"Cart count error: {e}")
        context['cart_count'] = 0
    
    return context