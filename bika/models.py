from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
import random
import string


# ==================== COLLABORATION / UNIT MODEL ====================

class Unit(models.Model):
    """Team/unit for collaborative visibility (e.g., same team sees same products)."""
    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=20, unique=True, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})" if self.code else self.name


# ==================== USER MODELS ====================

class CustomUser(AbstractUser):
    """Custom user model with different user types"""

    USER_TYPE_CHOICES = [
        ("customer", "Customer"),
        ("vendor", "Vendor"),
        ("admin", "Administrator"),
    ]

    ROLE_CHOICES = [
        ("staff", "Staff"),
        ("commander", "Commander"),
        ("admin", "Admin"),
    ]

    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default="customer")
    phone = models.CharField(max_length=20, blank=True)
    company = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    profile_picture = models.ImageField(upload_to="profiles/", blank=True, null=True)
    email_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)

    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True, related_name="users")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="staff")

    business_name = models.CharField(max_length=200, blank=True)
    business_description = models.TextField(blank=True)
    business_logo = models.ImageField(upload_to="business_logos/", blank=True, null=True)
    business_verified = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.username} ({self.get_user_type_display()})"

    def is_vendor(self) -> bool:
        return self.user_type == "vendor"

    def is_customer(self) -> bool:
        return self.user_type == "customer"

    def can_see_all_unit_products(self) -> bool:
        return self.role in {"commander", "admin"} or self.user_type == "admin"


# ==================== CORE MODELS ====================

class ProductCategory(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", blank=True, null=True)
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    parent = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="subcategories")

    class Meta:
        verbose_name_plural = "Product Categories"
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("bika:products_by_category", kwargs={"category_slug": self.slug})


class Product(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("active", "Active"),
        ("out_of_stock", "Out of Stock"),
        ("discontinued", "Discontinued"),
    ]

    CONDITION_CHOICES = [
        ("new", "New"),
        ("refurbished", "Refurbished"),
        ("used_like_new", "Used - Like New"),
        ("used_good", "Used - Good"),
        ("used_fair", "Used - Fair"),
    ]

    VISIBILITY_CHOICES = [
        ("unit", "Visible to same unit"),
        ("vendor", "Visible to same vendor"),
        ("private", "Only creator"),
    ]

    name = models.CharField(max_length=200)

    # ✅ CHANGED: allow blank and auto-generate in save()
    slug = models.SlugField(unique=True, blank=True)

    sku = models.CharField(max_length=100, unique=True, verbose_name="SKU")
    barcode = models.CharField(max_length=100, blank=True, unique=True, null=True)

    # ✅ CHANGED: allow empty description from mobile form
    description = models.TextField(blank=True, default="")
    short_description = models.TextField(max_length=300, blank=True)

    # ✅ CHANGED: category optional (mobile create can omit it)
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )

    tags = models.CharField(max_length=500, blank=True, help_text="Comma-separated tags")

    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Compare at Price")
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Cost Price")
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.0, verbose_name="Tax Rate (%)")

    stock_quantity = models.IntegerField(default=0)
    low_stock_threshold = models.IntegerField(default=5, verbose_name="Low Stock Alert")
    track_inventory = models.BooleanField(default=True)
    allow_backorders = models.BooleanField(default=False)

    brand = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    weight = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True, help_text="Weight in kg")
    dimensions = models.CharField(max_length=100, blank=True, help_text="L x W x H in cm")
    color = models.CharField(max_length=50, blank=True)
    size = models.CharField(max_length=50, blank=True)
    material = models.CharField(max_length=100, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default="new")
    is_featured = models.BooleanField(default=False)
    is_digital = models.BooleanField(default=False, verbose_name="Digital Product")

    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_products")
    visibility = models.CharField(max_length=20, choices=VISIBILITY_CHOICES, default="unit")

    # ✅ CHANGED: vendor optional (mobile create can omit it)
    vendor = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={"user_type": "vendor"},
        related_name="vendor_products",
    )

    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(blank=True, null=True)

    views_count = models.PositiveIntegerField(default=0, verbose_name="View Count")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["vendor", "created_at"]),
            models.Index(fields=["created_by", "created_at"]),
            models.Index(fields=["visibility", "status"]),
        ]

    def __str__(self):
        return f"{self.name} - {self.sku}"

    def get_absolute_url(self):
        return reverse("bika:product_detail", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        # ✅ Auto-generate slug if not provided
        if not self.slug:
            base_slug = slugify(self.name) or "product"
            slug_candidate = base_slug
            counter = 1
            while Product.objects.filter(slug=slug_candidate).exclude(pk=self.pk).exists():
                slug_candidate = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug_candidate

        if self.status == "active" and not self.published_at:
            self.published_at = timezone.now()

        super().save(*args, **kwargs)

    def is_visible_to(self, user) -> bool:
        """Collaboration visibility helper."""
        if not user or not user.is_authenticated:
            return False

        # global admins
        if getattr(user, "is_superuser", False) or getattr(user, "role", "") == "admin" or getattr(user, "user_type", "") == "admin":
            return True

        # creator always sees own
        if self.created_by_id == user.id:
            return True

        # private => creator only
        if self.visibility == "private":
            return False

        # vendor scope: only the product vendor (owner) and admins (handled above)
        if self.visibility == "vendor":
            return self.vendor_id == user.id

        # unit scope
        if self.visibility == "unit":
            my_unit_id = getattr(user, "unit_id", None)
            if not my_unit_id:
                return False
            creator_unit_id = getattr(self.created_by, "unit_id", None) if self.created_by else None
            vendor_unit_id = getattr(self.vendor, "unit_id", None) if self.vendor else None
            return my_unit_id in {creator_unit_id, vendor_unit_id}

        return False

    @property
    def is_in_stock(self):
        if not self.track_inventory:
            return True
        return self.stock_quantity > 0

    @property
    def is_low_stock(self):
        if not self.track_inventory:
            return False
        return 0 < self.stock_quantity <= self.low_stock_threshold

    @property
    def discount_percentage(self):
        if self.compare_price and self.compare_price > self.price:
            return round(((self.compare_price - self.price) / self.compare_price) * 100, 1)
        return 0

    @property
    def final_price(self):
        return self.price

    def get_related_products(self, limit=4):
        if self.category_id:
            return Product.objects.filter(category=self.category, status="active").exclude(id=self.id)[:limit]
        return Product.objects.filter(status="active").exclude(id=self.id)[:limit]


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/")
    alt_text = models.CharField(max_length=200, blank=True)
    display_order = models.IntegerField(default=0)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["display_order", "id"]

    def __str__(self):
        return f"Image for {self.product.name}"

    def save(self, *args, **kwargs):
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).update(is_primary=False)
        super().save(*args, **kwargs)


class ProductReview(models.Model):
    RATING_CHOICES = [(i, f"{i} Star" if i == 1 else f"{i} Stars") for i in range(1, 6)]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    rating = models.IntegerField(choices=RATING_CHOICES)
    title = models.CharField(max_length=200)
    comment = models.TextField()
    is_verified_purchase = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)
    helpful_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ["product", "user"]

    def __str__(self):
        return f"Review by {self.user.username} for {self.product.name}"


# ==================== E-COMMERCE MODELS ====================

class Wishlist(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["user", "product"]
        ordering = ["-added_at"]

    def __str__(self):
        return f"{self.user.username}'s wishlist - {self.product.name}"


class Cart(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["user", "product"]
        ordering = ["-added_at"]

    def __str__(self):
        return f"{self.user.username}'s cart - {self.product.name}"

    @property
    def total_price(self):
        # Decimal-safe multiply
        return self.product.final_price * self.quantity


class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    order_number = models.CharField(max_length=32, unique=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    shipping_address = models.TextField()
    billing_address = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{self.order_number} - {self.user.username}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            random_str = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            self.order_number = f"ORD{timezone.now().strftime('%Y%m%d')}{random_str}"
        super().save(*args, **kwargs)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    price = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.product.name} - {self.order.order_number}"

    @property
    def total_price(self):
        return self.price * self.quantity


# ==================== FRUIT MONITORING MODELS ====================

class FruitType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    scientific_name = models.CharField(max_length=200, blank=True)
    image = models.ImageField(upload_to="fruits/", blank=True, null=True)
    description = models.TextField(blank=True)

    optimal_temp_min = models.DecimalField(max_digits=5, decimal_places=2, default=2.0)
    optimal_temp_max = models.DecimalField(max_digits=5, decimal_places=2, default=8.0)
    optimal_humidity_min = models.DecimalField(max_digits=5, decimal_places=2, default=85.0)
    optimal_humidity_max = models.DecimalField(max_digits=5, decimal_places=2, default=95.0)
    optimal_light_max = models.IntegerField(default=100)
    optimal_co2_max = models.IntegerField(default=400)

    shelf_life_days = models.IntegerField(default=7)
    ethylene_sensitive = models.BooleanField(default=False)
    chilling_sensitive = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class StorageLocation(models.Model):
    name = models.CharField(max_length=200)
    address = models.TextField()
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    capacity = models.IntegerField(default=0)
    current_occupancy = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @property
    def available_capacity(self):
        return self.capacity - self.current_occupancy


class FruitBatch(models.Model):
    BATCH_STATUS = [
        ("pending", "Pending"),
        ("active", "Active Monitoring"),
        ("completed", "Completed"),
        ("discarded", "Discarded"),
    ]

    batch_number = models.CharField(max_length=50, unique=True)
    fruit_type = models.ForeignKey(FruitType, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.IntegerField(default=0)
    arrival_date = models.DateTimeField(default=timezone.now)
    expected_expiry = models.DateTimeField()
    supplier = models.CharField(max_length=200, blank=True)
    storage_location = models.ForeignKey(StorageLocation, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=BATCH_STATUS, default="pending")

    initial_quality = models.CharField(
        max_length=20,
        choices=[("excellent", "Excellent"), ("good", "Good"), ("fair", "Fair"), ("poor", "Poor")],
        default="good",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Fruit Batches"

    def __str__(self):
        return f"{self.batch_number} - {self.fruit_type.name}"

    @property
    def days_remaining(self):
        if self.expected_expiry:
            remaining = (self.expected_expiry - timezone.now()).days
            return max(remaining, 0)
        return 0


class FruitQualityReading(models.Model):
    QUALITY_CLASSES = [
        ("Fresh", "Fresh"),
        ("Good", "Good"),
        ("Fair", "Fair"),
        ("Poor", "Poor"),
        ("Rotten", "Rotten"),
    ]

    fruit_batch = models.ForeignKey(FruitBatch, on_delete=models.CASCADE, related_name="quality_readings")
    timestamp = models.DateTimeField(auto_now_add=True)

    temperature = models.DecimalField(max_digits=5, decimal_places=2)
    humidity = models.DecimalField(max_digits=5, decimal_places=2)
    light_intensity = models.DecimalField(max_digits=10, decimal_places=2, help_text="Light in lux")
    co2_level = models.IntegerField()

    actual_class = models.CharField(max_length=20, choices=QUALITY_CLASSES, blank=True)
    predicted_class = models.CharField(max_length=20, choices=QUALITY_CLASSES)
    confidence_score = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)

    ethylene_level = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Ethylene in ppm")
    weight_loss = models.DecimalField(max_digits=5, decimal_places=2, default=0.0, help_text="Weight loss percentage")
    firmness = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Firmness in N")

    model_used = models.CharField(max_length=50, blank=True)
    model_version = models.CharField(max_length=20, blank=True)

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["fruit_batch", "timestamp"])]

    def __str__(self):
        return f"{self.fruit_batch.batch_number} - {self.timestamp.strftime('%Y-%m-%d %H:%M')}"


class RealTimeSensorData(models.Model):
    SENSOR_TYPES = [
        ("temperature", "Temperature"),
        ("humidity", "Humidity"),
        ("light", "Light Intensity"),
        ("co2", "CO₂ Level"),
        ("ethylene", "Ethylene"),
        ("weight", "Weight"),
        ("firmness", "Firmness"),
        ("color", "Color"),
        ("vibration", "Vibration"),
        ("pressure", "Pressure"),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True)
    fruit_batch = models.ForeignKey(FruitBatch, on_delete=models.CASCADE, null=True, blank=True)
    sensor_type = models.CharField(max_length=50, choices=SENSOR_TYPES)
    value = models.FloatField()
    unit = models.CharField(max_length=20)
    location = models.ForeignKey(StorageLocation, on_delete=models.CASCADE, null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    predicted_class = models.CharField(max_length=20, blank=True)
    condition_confidence = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)

    class Meta:
        ordering = ["-recorded_at"]
        indexes = [models.Index(fields=["product", "sensor_type", "recorded_at"])]

    def __str__(self):
        return f"{self.sensor_type} - {self.value}{self.unit}"


# ==================== AI & DATASET MODELS ====================

class ProductDataset(models.Model):
    DATASET_TYPES = [
        ("anomaly_detection", "Anomaly Detection"),
        ("sales_forecast", "Sales Forecasting"),
        ("inventory_optimization", "Inventory Optimization"),
        ("quality_control", "Quality Control"),
    ]

    name = models.CharField(max_length=200)
    dataset_type = models.CharField(max_length=50, choices=DATASET_TYPES)
    description = models.TextField()
    data_file = models.FileField(upload_to="datasets/")
    columns = models.JSONField(default=dict)
    row_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.get_dataset_type_display()})"


class TrainedModel(models.Model):
    MODEL_TYPES = [
        ("anomaly_detection", "Anomaly Detection"),
        ("sales_forecast", "Sales Forecasting"),
        ("stock_prediction", "Stock Prediction"),
        ("fruit_quality", "Fruit Quality Prediction"),
    ]

    name = models.CharField(max_length=200)
    model_type = models.CharField(max_length=50, choices=MODEL_TYPES)
    dataset = models.ForeignKey(ProductDataset, on_delete=models.CASCADE)
    model_file = models.FileField(upload_to="trained_models/")
    accuracy = models.FloatField(null=True, blank=True)
    training_date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    feature_columns = models.JSONField(default=list)

    def __str__(self):
        return f"{self.name} - {self.get_model_type_display()}"


# ==================== ALERT & NOTIFICATION MODELS ====================

class ProductAlert(models.Model):
    ALERT_TYPES = [
        ("stock_low", "Low Stock"),
        ("expiry_near", "Near Expiry"),
        ("quality_issue", "Quality Issue"),
        ("temperature_anomaly", "Temperature Anomaly"),
        ("humidity_issue", "Humidity Issue"),
        ("ai_anomaly", "AI Detected Anomaly"),
    ]

    SEVERITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    ]

    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    alert_type = models.CharField(max_length=50, choices=ALERT_TYPES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    message = models.TextField()
    detected_by = models.CharField(max_length=50)  # ai_system, sensor_system, manual

    # ✅ FIX: your views use alert.details
    details = models.JSONField(default=dict, blank=True)

    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name="resolved_alerts")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_alert_type_display()} - {self.product.name}"


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ("product_alert", "Product Alert"),
        ("order_update", "Order Update"),
        ("system_alert", "System Alert"),
        ("urgent_alert", "Urgent Alert"),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPES)
    is_read = models.BooleanField(default=False)
    related_object_type = models.CharField(max_length=100, blank=True)
    related_object_id = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} - {self.user.username}"


# ==================== PAYMENT MODELS ====================

class Payment(models.Model):
    PAYMENT_METHODS = [
        ("mpesa", "M-Pesa (TZ)"),
        ("tigo_tz", "Tigo Pesa (TZ)"),
        ("airtel_tz", "Airtel Money (TZ)"),
        ("halotel_tz", "Halotel (TZ)"),
        ("mtn_rw", "MTN Mobile Money (RW)"),
        ("airtel_rw", "Airtel Money (RW)"),
        ("mtn_ug", "MTN Mobile Money (UG)"),
        ("airtel_ug", "Airtel Money (UG)"),
        ("mpesa_ke", "M-Pesa (KE)"),
        ("visa", "Visa Card"),
        ("mastercard", "MasterCard"),
        ("amex", "American Express"),
        ("paypal", "PayPal"),
        ("bank_transfer", "Bank Transfer"),
    ]

    PAYMENT_STATUS = [
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
        ("refunded", "Refunded"),
    ]

    CURRENCIES = [
        ("TZS", "Tanzanian Shilling"),
        ("RWF", "Rwandan Franc"),
        ("UGX", "Ugandan Shilling"),
        ("KES", "Kenyan Shilling"),
        ("USD", "US Dollar"),
        ("EUR", "Euro"),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payments")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, choices=CURRENCIES, default="TZS")
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default="pending")

    # ✅ FIX: must be NULLable, otherwise empty-string duplicates can crash with unique=True
    transaction_id = models.CharField(max_length=100, blank=True, null=True, unique=True)

    mobile_money_phone = models.CharField(max_length=20, blank=True)
    mobile_money_provider = models.CharField(max_length=50, blank=True)
    mobile_money_transaction_id = models.CharField(max_length=100, blank=True, null=True)

    card_last4 = models.CharField(max_length=4, blank=True)
    card_brand = models.CharField(max_length=20, blank=True)
    card_country = models.CharField(max_length=2, blank=True)

    payer_email = models.EmailField(blank=True)
    payer_country = models.CharField(max_length=2, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["transaction_id"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"Payment #{self.id} - {self.amount} {self.currency}"

    def is_successful(self):
        return self.status == "completed"


class PaymentGatewaySettings(models.Model):
    GATEWAY_CHOICES = [
        ("mpesa_tz", "M-Pesa Tanzania"),
        ("tigo_tz", "Tigo Pesa Tanzania"),
        ("airtel_tz", "Airtel Money Tanzania"),
        ("halotel_tz", "Halotel Tanzania"),
        ("mtn_rw", "MTN Rwanda"),
        ("airtel_rw", "Airtel Rwanda"),
        ("mtn_ug", "MTN Uganda"),
        ("airtel_ug", "Airtel Uganda"),
        ("mpesa_ke", "M-Pesa Kenya"),
        ("stripe", "Stripe"),
        ("paypal", "PayPal"),
    ]

    gateway = models.CharField(max_length=20, choices=GATEWAY_CHOICES, unique=True)
    is_active = models.BooleanField(default=False)
    display_name = models.CharField(max_length=100, blank=True)
    supported_countries = models.JSONField(default=list)
    supported_currencies = models.JSONField(default=list)

    api_key = models.CharField(max_length=255, blank=True)
    api_secret = models.CharField(max_length=255, blank=True)
    merchant_id = models.CharField(max_length=100, blank=True)
    webhook_secret = models.CharField(max_length=255, blank=True)

    base_url = models.URLField(blank=True)
    callback_url = models.URLField(blank=True)
    environment = models.CharField(max_length=10, default="sandbox", choices=[("sandbox", "Sandbox"), ("live", "Live")])

    transaction_fee_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)
    transaction_fee_fixed = models.DecimalField(max_digits=12, decimal_places=2, default=0.0)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.get_gateway_display()} Settings"


class CurrencyExchangeRate(models.Model):
    base_currency = models.CharField(max_length=3)
    target_currency = models.CharField(max_length=3)
    exchange_rate = models.DecimalField(max_digits=12, decimal_places=6)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["base_currency", "target_currency"]

    def __str__(self):
        return f"{self.base_currency}/{self.target_currency}: {self.exchange_rate}"


# ==================== SITE CONTENT MODELS ====================

class SiteInfo(models.Model):
    name = models.CharField(max_length=200, default="Bika")
    tagline = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    email = models.EmailField(default="contact@bika.com")
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    logo = models.ImageField(upload_to="site/logo/", blank=True, null=True)
    favicon = models.ImageField(upload_to="site/favicon/", blank=True, null=True)

    facebook_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)

    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.TextField(blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site Information"
        verbose_name_plural = "Site Information"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Ensure only one instance exists
        if not self.pk and SiteInfo.objects.exists():
            existing = SiteInfo.objects.first()
            for field in [
                "name", "tagline", "description", "email", "phone", "address",
                "facebook_url", "twitter_url", "instagram_url", "linkedin_url",
                "meta_title", "meta_description",
            ]:
                setattr(existing, field, getattr(self, field))

            if self.logo:
                existing.logo = self.logo
            if self.favicon:
                existing.favicon = self.favicon

            existing.save()
            return
        super().save(*args, **kwargs)


class Service(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    description = models.TextField()
    icon = models.CharField(max_length=100, help_text="Font Awesome icon class")
    image = models.ImageField(upload_to="services/", blank=True, null=True)
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("bika:service_detail", kwargs={"slug": self.slug})


class Testimonial(models.Model):
    name = models.CharField(max_length=200)
    position = models.CharField(max_length=200, blank=True)
    company = models.CharField(max_length=200, blank=True)
    content = models.TextField()
    image = models.ImageField(upload_to="testimonials/", blank=True, null=True)
    rating = models.IntegerField(choices=[(i, i) for i in range(1, 6)], default=5)
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_featured", "-created_at"]

    def __str__(self):
        return f"Testimonial from {self.name}"


class ContactMessage(models.Model):
    STATUS_CHOICES = [
        ("new", "New"),
        ("read", "Read"),
        ("replied", "Replied"),
        ("closed", "Closed"),
    ]

    name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="new")
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    replied_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.name} - {self.subject}"

    def mark_as_replied(self):
        self.status = "replied"
        self.replied_at = timezone.now()
        self.save()


class FAQ(models.Model):
    question = models.CharField(max_length=300)
    answer = models.TextField()
    display_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_order", "-created_at"]
        verbose_name = "FAQ"
        verbose_name_plural = "FAQs"

    def __str__(self):
        return self.question