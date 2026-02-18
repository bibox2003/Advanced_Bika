from rest_framework import serializers
from .models import Product, ProductImage, Cart


class ProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ["id", "image_url", "alt_text", "display_order", "is_primary"]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image:
            if request:
                return request.build_absolute_uri(obj.image.url)
            return obj.image.url
        return None


class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    primary_image = serializers.SerializerMethodField()
    is_in_stock = serializers.BooleanField(read_only=True)
    final_price = serializers.SerializerMethodField()

    # Collaboration fields
    created_by_name = serializers.SerializerMethodField()
    vendor_name = serializers.CharField(source="vendor.username", read_only=True)
    unit_name = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "sku",
            "price",
            "final_price",
            "stock_quantity",
            "is_in_stock",
            "status",
            "category_name",
            "primary_image",
            "short_description",
            # collaboration
            "created_by_name",
            "vendor_name",
            "unit_name",
            "created_at",
        ]

    def get_primary_image(self, obj):
        request = self.context.get("request")
        image = obj.images.filter(is_primary=True).first() or obj.images.first()
        if image and image.image:
            if request:
                return request.build_absolute_uri(image.image.url)
            return image.image.url
        return None

    def get_final_price(self, obj):
        return str(obj.final_price)

    def get_created_by_name(self, obj):
        return obj.created_by.username if obj.created_by else None

    def get_unit_name(self, obj):
        # Product may not have direct unit field; derive from creator/vendor unit
        if obj.created_by and getattr(obj.created_by, "unit", None):
            return obj.created_by.unit.name
        if obj.vendor and getattr(obj.vendor, "unit", None):
            return obj.vendor.unit.name
        return None


class ProductDetailSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    primary_image = serializers.SerializerMethodField()
    is_in_stock = serializers.BooleanField(read_only=True)
    final_price = serializers.SerializerMethodField()
    discount_percentage = serializers.FloatField(read_only=True)

    # Collaboration fields
    created_by_name = serializers.SerializerMethodField()
    vendor_name = serializers.CharField(source="vendor.username", read_only=True)
    unit_name = serializers.SerializerMethodField()
    visibility = serializers.CharField(read_only=True)

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
            "price",
            "compare_price",
            "final_price",
            "discount_percentage",
            "stock_quantity",
            "is_in_stock",
            "status",
            "condition",
            "brand",
            "model",
            "weight",
            "dimensions",
            "color",
            "size",
            "material",
            "category",
            "category_name",
            "primary_image",
            "images",
            # collaboration
            "created_by_name",
            "vendor_name",
            "unit_name",
            "visibility",
            "created_at",
            "updated_at",
        ]

    def get_primary_image(self, obj):
        request = self.context.get("request")
        image = obj.images.filter(is_primary=True).first() or obj.images.first()
        if image and image.image:
            if request:
                return request.build_absolute_uri(image.image.url)
            return image.image.url
        return None

    def get_final_price(self, obj):
        return str(obj.final_price)

    def get_created_by_name(self, obj):
        return obj.created_by.username if obj.created_by else None

    def get_unit_name(self, obj):
        if obj.created_by and getattr(obj.created_by, "unit", None):
            return obj.created_by.unit.name
        if obj.vendor and getattr(obj.vendor, "unit", None):
            return obj.vendor.unit.name
        return None


class CartSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_image = serializers.SerializerMethodField()
    unit_price = serializers.SerializerMethodField()
    total_price = serializers.SerializerMethodField()
    product_stock = serializers.IntegerField(source="product.stock_quantity", read_only=True)

    # Helpful display fields
    product_created_by = serializers.SerializerMethodField()
    product_unit_name = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = [
            "id",
            "product",
            "product_name",
            "product_image",
            "quantity",
            "unit_price",
            "total_price",
            "product_stock",
            "product_created_by",
            "product_unit_name",
            "added_at",
            "updated_at",
        ]

    def get_product_image(self, obj):
        request = self.context.get("request")
        image = obj.product.images.filter(is_primary=True).first() or obj.product.images.first()
        if image and image.image:
            if request:
                return request.build_absolute_uri(image.image.url)
            return image.image.url
        return None

    def get_unit_price(self, obj):
        return str(obj.product.final_price)

    def get_total_price(self, obj):
        return str(obj.total_price)

    def get_product_created_by(self, obj):
        return obj.product.created_by.username if obj.product.created_by else None

    def get_product_unit_name(self, obj):
        p = obj.product
        if p.created_by and getattr(p.created_by, "unit", None):
            return p.created_by.unit.name
        if p.vendor and getattr(p.vendor, "unit", None):
            return p.vendor.unit.name
        return None
