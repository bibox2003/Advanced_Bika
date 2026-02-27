# Advanced_Bika/bika/product_write_serializers.py

from django.utils.text import slugify
from rest_framework import serializers
from django.contrib.auth import get_user_model

from .models import Product

User = get_user_model()


class ProductWriteSerializer(serializers.ModelSerializer):
    """
    Serializer used for CREATE/UPDATE from the mobile app (Flutter).
    Handles:
    - optional slug generation
    - optional sku generation
    - Flutter `active` -> Product.status mapping
    - optional category/vendor fields
    - safe defaults for stock/inventory/status
    - auto vendor/category assignment when Flutter doesn't send them
    """

    slug = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    short_description = serializers.CharField(required=False, allow_blank=True, default="")
    barcode = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    sku = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    # Flutter compatibility: app sends `active`
    active = serializers.BooleanField(write_only=True, required=False)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "sku",
            "barcode",
            "price",
            "stock_quantity",
            "status",
            "track_inventory",
            "low_stock_threshold",
            "visibility",
            "description",
            "short_description",
            "condition",
            "brand",
            "model",
            "color",
            "size",
            "material",
            "category",
            "vendor",
            "active",
        ]
        read_only_fields = ["id"]

        extra_kwargs = {
            "category": {"required": False, "allow_null": True},
            "vendor": {"required": False, "allow_null": True},
            "price": {"required": False},
            "stock_quantity": {"required": False},
            "status": {"required": False},
            "track_inventory": {"required": False},
            "low_stock_threshold": {"required": False},
            "visibility": {"required": False},
            "condition": {"required": False},
        }

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _get_category_model(self):
        """
        Dynamically fetch the related model used by Product.category FK.
        This avoids hardcoding a model name like `Category`.
        """
        try:
            return Product._meta.get_field("category").remote_field.model
        except Exception:
            return None

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
        base = "SKU"
        n = 1001
        while Product.objects.filter(sku=f"{base}{n}").exists():
            n += 1
        return f"{base}{n}"

    def _resolve_vendor_for_request(self, request):
        """
        Return a valid vendor user for Product.vendor when frontend doesn't send vendor.
        Priority:
        1) request.user if vendor
        2) first vendor account in DB (fallback for admin-created products)
        3) request.user (last fallback if Product.vendor points to User)
        4) None
        """
        if not request or not getattr(request, "user", None) or not request.user.is_authenticated:
            return None

        user = request.user

        # Case 1: logged in user is vendor
        if getattr(user, "user_type", None) == "vendor":
            return user

        # Case 2: fallback vendor account
        fallback_vendor = (
            User.objects.filter(user_type="vendor", is_active=True)
            .order_by("id")
            .first()
        )
        if fallback_vendor:
            return fallback_vendor

        # Case 3: last fallback
        return user

    def _resolve_category(self, incoming_value):
        """
        Resolve category sent by Flutter.
        Accepts:
        - integer ID
        - numeric string ID
        - category name (string)
        - None -> fallback to first category / create 'General'
        """
        CategoryModel = self._get_category_model()
        if CategoryModel is None:
            return None

        # If already a category instance
        if isinstance(incoming_value, CategoryModel):
            return incoming_value

        # If frontend sent something
        if incoming_value not in (None, ""):
            # Try numeric ID
            try:
                cat_id = int(incoming_value)
                obj = CategoryModel.objects.filter(pk=cat_id).first()
                if obj:
                    return obj
            except (TypeError, ValueError):
                pass

            # Try name
            name = str(incoming_value).strip()
            if name:
                # Find by name if field exists
                if hasattr(CategoryModel, "name"):
                    obj = CategoryModel.objects.filter(name__iexact=name).first()
                    if obj:
                        return obj

                # Create by name if possible
                create_data = {}
                if hasattr(CategoryModel, "name"):
                    create_data["name"] = name

                if hasattr(CategoryModel, "slug"):
                    base_slug = slugify(name) or "general"
                    slug = base_slug
                    n = 2
                    while CategoryModel.objects.filter(slug=slug).exists():
                        slug = f"{base_slug}-{n}"
                        n += 1
                    create_data["slug"] = slug

                # Only create if we have enough fields
                try:
                    if create_data:
                        return CategoryModel.objects.create(**create_data)
                except Exception:
                    # If creation fails due to other required fields, continue to fallback
                    pass

        # Fallback: first category
        first_obj = CategoryModel.objects.order_by("id").first()
        if first_obj:
            return first_obj

        # Last fallback: try creating "General"
        try:
            create_data = {}
            if hasattr(CategoryModel, "name"):
                create_data["name"] = "General"

            if hasattr(CategoryModel, "slug"):
                base_slug = "general"
                slug = base_slug
                n = 2
                while CategoryModel.objects.filter(slug=slug).exists():
                    slug = f"{base_slug}-{n}"
                    n += 1
                create_data["slug"] = slug

            if create_data:
                return CategoryModel.objects.create(**create_data)
        except Exception:
            pass

        return None

    # -------------------------------------------------------------------------
    # Field-level validation
    # -------------------------------------------------------------------------
    def validate_stock_quantity(self, value):
        if value is None:
            return value
        if int(value) < 0:
            raise serializers.ValidationError("stock_quantity cannot be negative.")
        return value

    # -------------------------------------------------------------------------
    # Object-level validation + normalization
    # -------------------------------------------------------------------------
    def validate(self, attrs):
        name = (attrs.get("name") or "").strip()
        incoming_slug = (attrs.get("slug") or "").strip()
        incoming_sku = (attrs.get("sku") or "").strip() if attrs.get("sku") is not None else ""

        # Normalize text fields
        attrs["description"] = (attrs.get("description") or "").strip()
        attrs["short_description"] = (attrs.get("short_description") or "").strip()

        # Defaults for create only
        if self.instance is None:
            if "stock_quantity" not in attrs:
                attrs["stock_quantity"] = 0
            if "track_inventory" not in attrs:
                attrs["track_inventory"] = True

        # Flutter `active` -> `status`
        active = attrs.pop("active", None)
        if active is not None and "status" not in attrs:
            attrs["status"] = "active" if active else "draft"

        # Default status (create only)
        if self.instance is None and not attrs.get("status"):
            attrs["status"] = "active"

        # Inventory validation
        track_inventory = attrs.get(
            "track_inventory",
            getattr(self.instance, "track_inventory", True) if self.instance else True,
        )
        stock = attrs.get(
            "stock_quantity",
            getattr(self.instance, "stock_quantity", None) if self.instance else None
        )

        if track_inventory and stock is not None and int(stock) < 0:
            raise serializers.ValidationError({"stock_quantity": "Stock cannot be below zero."})

        # Slug handling
        if hasattr(Product, "slug"):
            if not incoming_slug:
                source_name = name or getattr(self.instance, "name", "") or "product"
                if self.instance is not None and "name" in attrs and "slug" not in attrs:
                    attrs["slug"] = self.instance.slug
                elif self.instance is None:
                    attrs["slug"] = self._make_unique_slug(source_name, current_instance=self.instance)
            else:
                attrs["slug"] = self._make_unique_slug(incoming_slug, current_instance=self.instance)

        # SKU handling
        if not incoming_sku:
            if self.instance is None:
                attrs["sku"] = self._make_unique_sku()
            else:
                attrs["sku"] = self.instance.sku

        # Ensure vendor exists for create (if required)
        if self.instance is None and hasattr(Product, "vendor"):
            if attrs.get("vendor") is None:
                request = self.context.get("request")
                resolved_vendor = self._resolve_vendor_for_request(request)
                if resolved_vendor is None:
                    raise serializers.ValidationError({
                        "vendor": "No vendor could be assigned. Create a vendor account first or send vendor ID."
                    })
                attrs["vendor"] = resolved_vendor

        # Ensure category exists for create (if required)
        if self.instance is None and hasattr(Product, "category"):
            if attrs.get("category") is None:
                resolved_category = self._resolve_category(None)
            else:
                resolved_category = self._resolve_category(attrs.get("category"))

            if resolved_category is None:
                raise serializers.ValidationError({
                    "category": "No category could be assigned. Create a category first or send category ID."
                })

            attrs["category"] = resolved_category

        return attrs

    # -------------------------------------------------------------------------
    # Create / Update hooks
    # -------------------------------------------------------------------------
    def create(self, validated_data):
        request = self.context.get("request")

        # Auto-set created_by
        if hasattr(Product, "created_by") and request and getattr(request, "user", None):
            user = request.user
            if user and user.is_authenticated and "created_by" not in validated_data:
                validated_data["created_by"] = user

        # Safety: vendor
        if hasattr(Product, "vendor") and validated_data.get("vendor") is None:
            resolved_vendor = self._resolve_vendor_for_request(request)
            if resolved_vendor is None:
                raise serializers.ValidationError(
                    {"vendor": "Vendor is required. No vendor account available to assign."}
                )
            validated_data["vendor"] = resolved_vendor

        # Safety: category
        if hasattr(Product, "category") and validated_data.get("category") is None:
            resolved_category = self._resolve_category(None)
            if resolved_category is None:
                raise serializers.ValidationError(
                    {"category": "Category is required. No category available to assign."}
                )
            validated_data["category"] = resolved_category

        return super().create(validated_data)

    def update(self, instance, validated_data):
        # Keep existing slug unless explicitly sent
        if hasattr(instance, "slug"):
            if "name" in validated_data and "slug" not in validated_data:
                validated_data["slug"] = instance.slug

        # Keep existing vendor unless explicitly sent
        if hasattr(instance, "vendor") and "vendor" not in validated_data:
            validated_data["vendor"] = instance.vendor

        # Keep existing category unless explicitly sent
        if hasattr(instance, "category") and "category" not in validated_data:
            validated_data["category"] = instance.category

        return super().update(instance, validated_data)