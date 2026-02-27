# bika/api_serializers.py
# COMPLETE (Products + Cart + Inventory + Dashboard serializers)

from decimal import Decimal
from django.utils.text import slugify
from rest_framework import serializers


from .models import Product, ProductImage, Cart, ProductCategory, CustomUser


# -----------------------------------------------------------------------------
# Product Images
# -----------------------------------------------------------------------------
class ProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ["id", "image_url", "alt_text", "display_order", "is_primary"]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if not obj.image:
            return None
        url = obj.image.url
        return request.build_absolute_uri(url) if request else url


# -----------------------------------------------------------------------------
# Category / Vendor helper serializers (for dropdowns / API lists)
# -----------------------------------------------------------------------------
class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ["id", "name", "slug"]


class VendorSerializer(serializers.ModelSerializer):
    """
    In your project, 'vendor' is a CustomUser with user_type='vendor'.
    """
    name = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ["id", "username", "name", "business_name"]

    def get_name(self, obj):
        # Flutter compatibility: returns a readable display name
        return obj.business_name or obj.get_full_name() or obj.username


# -----------------------------------------------------------------------------
# DASHBOARD SUMMARY
# Used by GET /api/v1/dashboard/summary/
# -----------------------------------------------------------------------------
class DashboardSummarySerializer(serializers.Serializer):
    total_products = serializers.IntegerField()
    active_products = serializers.IntegerField()
    inactive_products = serializers.IntegerField()
    low_stock_products = serializers.IntegerField()

    cart_items = serializers.IntegerField()
    cart_quantity_total = serializers.IntegerField()
    cart_total_amount = serializers.FloatField()


# -----------------------------------------------------------------------------
# INVENTORY: stock adjust request serializer
# Used by PATCH /api/v1/products/<id>/stock/ body: {"delta": 1}
# -----------------------------------------------------------------------------
class StockAdjustSerializer(serializers.Serializer):
    delta = serializers.IntegerField()

    def validate_delta(self, value):
        if value == 0:
            raise serializers.ValidationError("delta cannot be 0.")
        return value


# -----------------------------------------------------------------------------
# PRODUCTS (WRITE)
# Fixes create errors:
# - slug auto-generated if missing
# - description optional
# - accepts "active" from Flutter and maps to status
# - category/vendor optional
# -----------------------------------------------------------------------------
class ProductWriteSerializer(serializers.ModelSerializer):
    slug = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    short_description = serializers.CharField(required=False, allow_blank=True, default="")
    barcode = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    sku = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    # Flutter sends `active`; map it internally to Product.status
    active = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "sku",
            "barcode",
            "description",
            "short_description",
            "status",
            "condition",
            "is_featured",
            "track_inventory",
            "stock_quantity",
            "low_stock_threshold",
            "category",
            "vendor",
            "price",
            "compare_price",
            "active",  # write-only helper
        ]
        read_only_fields = ["id"]

        extra_kwargs = {
            # Optional (matches your current usage)
            "category": {"required": False, "allow_null": True},
            "vendor": {"required": False, "allow_null": True},
            "price": {"required": False},
            "compare_price": {"required": False, "allow_null": True},
            "stock_quantity": {"required": False},
            "low_stock_threshold": {"required": False},
            "track_inventory": {"required": False},
            "status": {"required": False},
            "condition": {"required": False},
            "is_featured": {"required": False},
        }

    def _make_unique_slug(self, base_name: str, current_instance=None) -> str:
        base = slugify(base_name or "") or "product"
        slug = base
        n = 2

        qs = Product.objects.all()
        if current_instance is not None:
            qs = qs.exclude(pk=current_instance.pk)

        while qs.filter(slug=slug).exists():
            slug = f"{base}-{n}"
            n += 1
        return slug

    def _make_unique_sku(self) -> str:
        """
        Generates SKU only if frontend doesn't send one.
        """
        base = "SKU"
        n = 1001
        while Product.objects.filter(sku=f"{base}{n}").exists():
            n += 1
        return f"{base}{n}"

    def validate(self, attrs):
        name = (attrs.get("name") or "").strip()
        incoming_slug = (attrs.get("slug") or "").strip()
        incoming_sku = (attrs.get("sku") or "").strip() if attrs.get("sku") is not None else ""

        # Defaults
        if "stock_quantity" not in attrs:
            attrs["stock_quantity"] = 0

        if "track_inventory" not in attrs:
            attrs["track_inventory"] = True

        attrs["description"] = (attrs.get("description") or "").strip()
        attrs["short_description"] = (attrs.get("short_description") or "").strip()

        # Flutter active -> status
        active = attrs.pop("active", None)
        if active is not None and "status" not in attrs:
            attrs["status"] = "active" if active else "draft"

        # Default status if omitted
        if not attrs.get("status"):
            attrs["status"] = "active"

        # Slug handling
        if not incoming_slug:
            source_name = name or getattr(self.instance, "name", "") or "product"
            attrs["slug"] = self._make_unique_slug(source_name, current_instance=self.instance)
        else:
            attrs["slug"] = self._make_unique_slug(incoming_slug, current_instance=self.instance)

        # SKU handling (your model requires unique sku)
        if not incoming_sku:
            if self.instance is None:  # create only
                attrs["sku"] = self._make_unique_sku()
            else:
                attrs["sku"] = self.instance.sku

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")

        # Auto-attach creator if model has created_by
        if hasattr(Product, "created_by") and request and getattr(request, "user", None):
            user = request.user
            if user and user.is_authenticated and "created_by" not in validated_data:
                validated_data["created_by"] = user

        # Optional: if vendor omitted and user is vendor, use current user
        if "vendor" not in validated_data or validated_data.get("vendor") is None:
            if request and getattr(request, "user", None) and request.user.is_authenticated:
                if getattr(request.user, "user_type", None) == "vendor":
                    validated_data["vendor"] = request.user

        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Keep existing slug if name changes but slug isn't explicitly provided
        if "name" in validated_data and "slug" not in validated_data:
            validated_data["slug"] = instance.slug
        return super().update(instance, validated_data)


# -----------------------------------------------------------------------------
# PRODUCTS (READ - LIST)
# -----------------------------------------------------------------------------
class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    vendor_username = serializers.CharField(source="vendor.username", read_only=True)
    vendor_name = serializers.SerializerMethodField()

    primary_image = serializers.SerializerMethodField()
    visibility = serializers.CharField(read_only=True)
    created_by_id = serializers.IntegerField(source="created_by.id", read_only=True, allow_null=True)

    price = serializers.SerializerMethodField()
    final_price = serializers.SerializerMethodField()

    # Flutter compatibility aliases
    is_in_stock = serializers.SerializerMethodField()
    active = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "sku",
            "barcode",
            "short_description",
            "status",
            "active",
            "condition",
            "is_featured",
            "track_inventory",
            "stock_quantity",
            "low_stock_threshold",
            "category",
            "category_name",
            "vendor",
            "vendor_username",
            "vendor_name",
            "created_by_id",
            "visibility",
            "price",
            "final_price",
            "is_in_stock",
            "primary_image",
            "created_at",
            "updated_at",
        ]

    def get_price(self, obj):
        return str(obj.price) if obj.price is not None else "0.00"

    def get_final_price(self, obj):
        return str(getattr(obj, "final_price", obj.price))

    def get_is_in_stock(self, obj):
        return bool(getattr(obj, "is_in_stock", (obj.stock_quantity or 0) > 0))

    def get_active(self, obj):
        return str(getattr(obj, "status", "")).lower() == "active"

    def get_vendor_name(self, obj):
        vendor = getattr(obj, "vendor", None)
        if not vendor:
            return None
        return getattr(vendor, "business_name", None) or vendor.get_full_name() or vendor.username

    def get_primary_image(self, obj):
        request = self.context.get("request")
        img = obj.images.filter(is_primary=True).first() or obj.images.first()
        if not img or not img.image:
            return None
        url = img.image.url
        return request.build_absolute_uri(url) if request else url


# -----------------------------------------------------------------------------
# PRODUCTS (READ - DETAIL)
# -----------------------------------------------------------------------------
class ProductDetailSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    vendor_username = serializers.CharField(source="vendor.username", read_only=True)
    vendor_name = serializers.SerializerMethodField()

    images = ProductImageSerializer(many=True, read_only=True)

    visibility = serializers.CharField(read_only=True)
    created_by_id = serializers.IntegerField(source="created_by.id", read_only=True, allow_null=True)

    price = serializers.SerializerMethodField()
    compare_price = serializers.SerializerMethodField()
    final_price = serializers.SerializerMethodField()
    discount_percentage = serializers.SerializerMethodField()

    is_in_stock = serializers.SerializerMethodField()
    is_low_stock = serializers.SerializerMethodField()
    active = serializers.SerializerMethodField()  # Flutter alias

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "sku",
            "barcode",
            "description",
            "short_description",
            "tags",
            "status",
            "active",
            "condition",
            "is_featured",
            "is_digital",
            "track_inventory",
            "allow_backorders",
            "stock_quantity",
            "low_stock_threshold",
            "is_in_stock",
            "is_low_stock",
            "brand",
            "model",
            "weight",
            "dimensions",
            "color",
            "size",
            "material",
            "tax_rate",
            "category",
            "category_name",
            "vendor",
            "vendor_username",
            "vendor_name",
            "created_by_id",
            "visibility",
            "price",
            "compare_price",
            "final_price",
            "discount_percentage",
            "images",
            "views_count",
            "published_at",
            "created_at",
            "updated_at",
        ]

    def get_price(self, obj):
        return str(obj.price) if obj.price is not None else "0.00"

    def get_compare_price(self, obj):
        return str(obj.compare_price) if obj.compare_price is not None else None

    def get_final_price(self, obj):
        return str(getattr(obj, "final_price", obj.price))

    def get_discount_percentage(self, obj):
        try:
            return float(getattr(obj, "discount_percentage", 0))
        except Exception:
            return 0

    def get_is_in_stock(self, obj):
        return bool(getattr(obj, "is_in_stock", True))

    def get_is_low_stock(self, obj):
        return bool(getattr(obj, "is_low_stock", False))

    def get_active(self, obj):
        return str(getattr(obj, "status", "")).lower() == "active"

    def get_vendor_name(self, obj):
        vendor = getattr(obj, "vendor", None)
        if not vendor:
            return None
        return getattr(vendor, "business_name", None) or vendor.get_full_name() or vendor.username


# -----------------------------------------------------------------------------
# CART
# -----------------------------------------------------------------------------
class CartItemProductMiniSerializer(serializers.ModelSerializer):
    primary_image = serializers.SerializerMethodField()
    final_price = serializers.SerializerMethodField()
    is_in_stock = serializers.SerializerMethodField()
    active = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "sku",
            "slug",
            "status",
            "active",
            "track_inventory",
            "stock_quantity",
            "is_in_stock",
            "final_price",
            "primary_image",
        ]

    def get_primary_image(self, obj):
        request = self.context.get("request")
        img = obj.images.filter(is_primary=True).first() or obj.images.first()
        if not img or not img.image:
            return None
        url = img.image.url
        return request.build_absolute_uri(url) if request else url

    def get_final_price(self, obj):
        return str(getattr(obj, "final_price", obj.price))

    def get_is_in_stock(self, obj):
        return bool(getattr(obj, "is_in_stock", (obj.stock_quantity or 0) > 0))

    def get_active(self, obj):
        return str(getattr(obj, "status", "")).lower() == "active"


class CartSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(source="product.id", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    unit_price = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()
    stock_quantity = serializers.IntegerField(source="product.stock_quantity", read_only=True)
    is_in_stock = serializers.BooleanField(source="product.is_in_stock", read_only=True)
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            "id",
            "product_id",
            "product_name",
            "quantity",
            "unit_price",
            "total_price",
            "stock_quantity",
            "is_in_stock",
            "image_url",
        ]

    def get_unit_price(self, obj):
        return str(obj.product.final_price)

    def get_total_price(self, obj):
        return str(obj.product.final_price * obj.quantity)

    def get_image_url(self, obj):
        request = self.context.get("request")
        first_image = obj.product.images.first() if hasattr(obj.product, "images") else None
        if not first_image:
            return None

        # adjust field name if your image model uses a different field (image/file/photo)
        img = getattr(first_image, "image", None) or getattr(first_image, "file", None)
        if not img:
            return None

        try:
            url = img.url
        except Exception:
            return None

        return request.build_absolute_uri(url) if request else url