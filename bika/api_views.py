# Advanced_Bika/bika/api_views.py

from decimal import Decimal

from django.db.models import Q, Sum, F
from django.db import transaction
from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework import generics, status
from rest_framework_simplejwt.tokens import RefreshToken

from .models import Product, Cart, Order, OrderItem, Payment
from .api_serializers import ProductListSerializer, ProductDetailSerializer, CartSerializer
from .product_write_serializers import ProductWriteSerializer   # ✅ IMPORTANT
from .checkout_serializers import CreateOrderSerializer
from .orders_serializers import OrderListSerializer, OrderDetailSerializer


# -----------------------------------------------------------------------------
# Visibility helper
# -----------------------------------------------------------------------------
def _product_visibility_queryset_for_user(user):
    """
    Product visibility rules:
    - superuser/admin sees all active products
    - Others:
      * own products always visible
      * private => creator only
      * unit => same unit
      * vendor => vendor owner
    """
    base = (
        Product.objects.filter(status="active")
        .select_related("category", "vendor", "created_by", "created_by__unit", "vendor__unit")
        .prefetch_related("images")
    )

    if (
        getattr(user, "is_superuser", False)
        or getattr(user, "user_type", "") == "admin"
        or getattr(user, "role", "") == "admin"
    ):
        return base.order_by("-created_at")

    user_unit_id = getattr(user, "unit_id", None)

    qs = base.filter(
        Q(created_by=user)
        | Q(visibility="private", created_by=user)
        | (
            Q(visibility="unit")
            & (Q(created_by__unit_id=user_unit_id) | Q(vendor__unit_id=user_unit_id))
        )
        | Q(visibility="vendor", vendor=user)
    ).distinct()

    return qs.order_by("-created_at")


def _can_adjust_stock(user, product):
    if getattr(user, "is_superuser", False):
        return True
    if getattr(user, "user_type", "") == "admin" or getattr(user, "role", "") == "admin":
        return True
    if product.created_by_id == user.id:
        return True
    if product.vendor_id == user.id:
        return True
    return False


# -----------------------------------------------------------------------------
# User
# -----------------------------------------------------------------------------
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "user_type": getattr(user, "user_type", None),
            "phone": getattr(user, "phone", ""),
            "company": getattr(user, "company", ""),
            "role": getattr(user, "role", ""),
            "unit": getattr(getattr(user, "unit", None), "name", None),
        })


# -----------------------------------------------------------------------------
# Dashboard Summary
# -----------------------------------------------------------------------------
class DashboardSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        visible_products = _product_visibility_queryset_for_user(request.user)

        total_count = visible_products.count()
        active_count = visible_products.filter(status="active").count()
        out_of_stock_count = visible_products.filter(status="out_of_stock").count()

        low_stock_count = visible_products.filter(
            track_inventory=True,
            stock_quantity__gt=0,
            stock_quantity__lte=F("low_stock_threshold"),
        ).count()

        cart_qs = Cart.objects.filter(user=request.user).select_related("product")
        cart_items_count = cart_qs.count()
        cart_total_qty = cart_qs.aggregate(total_qty=Sum("quantity"))["total_qty"] or 0

        cart_total_value = Decimal("0.00")
        for item in cart_qs:
            cart_total_value += Decimal(str(item.product.final_price)) * Decimal(str(item.quantity))

        recent_products = visible_products.order_by("-created_at")[:5]
        recent_data = [{
            "id": p.id,
            "name": p.name,
            "stock_quantity": p.stock_quantity,
            "status": p.status,
            "price": str(p.final_price),
            "created_at": p.created_at,
        } for p in recent_products]

        return Response({
            "products": {
                "total": total_count,
                "active": active_count,
                "out_of_stock": out_of_stock_count,
                "low_stock": low_stock_count,
            },
            "cart": {
                "items_count": cart_items_count,
                "total_quantity": cart_total_qty,
                "total_value": str(cart_total_value),
            },
            "recent_products": recent_data,
        }, status=status.HTTP_200_OK)


# -----------------------------------------------------------------------------
# Products
# -----------------------------------------------------------------------------
class ProductListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProductListSerializer

    def get_queryset(self):
        mine_only = self.request.query_params.get("mine") == "1"
        if mine_only:
            return (
                Product.objects.filter(status="active", created_by=self.request.user)
                .select_related("category", "vendor", "created_by", "created_by__unit", "vendor__unit")
                .prefetch_related("images")
                .order_by("-created_at")
            )
        return _product_visibility_queryset_for_user(self.request.user)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx


class ProductDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProductDetailSerializer
    lookup_field = "id"

    def get_queryset(self):
        return _product_visibility_queryset_for_user(self.request.user)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx


class ProductCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # ✅ Use ProductWriteSerializer for create
        serializer = ProductWriteSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            product = serializer.save(created_by=request.user)
            return Response(
                ProductDetailSerializer(product, context={"request": request}).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProductUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, id):
        try:
            product = Product.objects.select_related("vendor", "created_by").get(id=id)
        except Product.DoesNotExist:
            return Response({"detail": "Product not found."}, status=status.HTTP_404_NOT_FOUND)

        if not _can_adjust_stock(request.user, product):
            return Response(
                {"detail": "You do not have permission to edit this product."},
                status=status.HTTP_403_FORBIDDEN
            )

        # ✅ Use ProductWriteSerializer for update
        serializer = ProductWriteSerializer(
            product,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        if serializer.is_valid():
            updated = serializer.save()
            return Response(
                ProductDetailSerializer(updated, context={"request": request}).data,
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProductDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, id):
        try:
            product = Product.objects.select_related("vendor", "created_by").get(id=id)
        except Product.DoesNotExist:
            return Response({"detail": "Product not found."}, status=status.HTTP_404_NOT_FOUND)

        if not _can_adjust_stock(request.user, product):
            return Response(
                {"detail": "You do not have permission to delete this product."},
                status=status.HTTP_403_FORBIDDEN
            )

        product.delete()
        return Response({"detail": "Product deleted successfully."}, status=status.HTTP_200_OK)


class ProductStockAdjustView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, id):
        try:
            product = Product.objects.select_related("vendor", "created_by").get(id=id, status="active")
        except Product.DoesNotExist:
            return Response({"detail": "Product not found."}, status=status.HTTP_404_NOT_FOUND)

        if not _can_adjust_stock(request.user, product):
            return Response(
                {"detail": "You do not have permission to adjust stock for this product."},
                status=status.HTTP_403_FORBIDDEN
            )

        delta = request.data.get("delta")
        if delta is None:
            return Response({"detail": "delta is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            delta = int(delta)
        except (TypeError, ValueError):
            return Response({"detail": "delta must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

        if delta == 0:
            return Response({"detail": "delta cannot be 0."}, status=status.HTTP_400_BAD_REQUEST)

        new_qty = product.stock_quantity + delta
        if product.track_inventory and new_qty < 0:
            return Response(
                {"detail": "Stock cannot go below zero.", "current_stock": product.stock_quantity},
                status=status.HTTP_400_BAD_REQUEST
            )

        product.stock_quantity = max(new_qty, 0) if product.track_inventory else new_qty
        if product.track_inventory:
            if product.stock_quantity <= 0:
                product.status = "out_of_stock"
            elif product.status == "out_of_stock" and product.stock_quantity > 0:
                product.status = "active"

        product.save(update_fields=["stock_quantity", "status", "updated_at"])

        return Response({
            "detail": "Stock updated successfully.",
            "product_id": product.id,
            "name": product.name,
            "delta": delta,
            "stock_quantity": product.stock_quantity,
            "status": product.status,
            "is_in_stock": product.is_in_stock,
        }, status=status.HTTP_200_OK)


# -----------------------------------------------------------------------------
# Cart
# -----------------------------------------------------------------------------
class CartListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CartSerializer

    def get_queryset(self):
        return (
            Cart.objects.filter(user=self.request.user)
            .select_related("product", "product__created_by", "product__vendor")
            .prefetch_related("product__images")
            .order_by("-added_at")
        )

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request
        return ctx


class AddToCartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        product_id = request.data.get("product_id")
        quantity_raw = request.data.get("quantity", 1)

        if not product_id:
            return Response({"detail": "product_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            quantity = int(quantity_raw)
        except (TypeError, ValueError):
            return Response({"detail": "quantity must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

        if quantity < 1:
            return Response({"detail": "quantity must be at least 1."}, status=status.HTTP_400_BAD_REQUEST)

        visible_qs = _product_visibility_queryset_for_user(request.user)
        try:
            product = visible_qs.get(id=product_id)
        except Product.DoesNotExist:
            return Response(
                {"detail": "Product not found or not visible to your account."},
                status=status.HTTP_404_NOT_FOUND
            )

        cart_item, created = Cart.objects.get_or_create(
            user=request.user,
            product=product,
            defaults={"quantity": quantity},
        )

        if not created:
            cart_item.quantity += quantity
            cart_item.save(update_fields=["quantity", "updated_at"])

        serializer = CartSerializer(cart_item, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class UpdateCartItemView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, item_id):
        quantity = request.data.get("quantity")
        if quantity is None:
            return Response({"detail": "quantity is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return Response({"detail": "quantity must be an integer."}, status=status.HTTP_400_BAD_REQUEST)

        if quantity < 1:
            return Response({"detail": "quantity must be at least 1."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            item = Cart.objects.select_related("product").get(id=item_id, user=request.user)
        except Cart.DoesNotExist:
            return Response({"detail": "Cart item not found."}, status=status.HTTP_404_NOT_FOUND)

        item.quantity = quantity
        item.save(update_fields=["quantity", "updated_at"])
        serializer = CartSerializer(item, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class RemoveCartItemView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, item_id):
        try:
            item = Cart.objects.get(id=item_id, user=request.user)
        except Cart.DoesNotExist:
            return Response({"detail": "Cart item not found."}, status=status.HTTP_404_NOT_FOUND)

        item.delete()
        return Response({"detail": "Item removed."}, status=status.HTTP_200_OK)


# -----------------------------------------------------------------------------
# Checkout
# -----------------------------------------------------------------------------
class CheckoutPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cart_items = Cart.objects.filter(user=request.user).select_related("product").order_by("-added_at")

        items = []
        subtotal = Decimal("0.00")
        total_items = 0

        for c in cart_items:
            unit_price = Decimal(str(c.product.final_price))
            line_total = unit_price * Decimal(str(c.quantity))
            subtotal += line_total
            total_items += c.quantity

            items.append({
                "cart_item_id": c.id,
                "product_id": c.product_id,
                "product_name": c.product.name,
                "quantity": c.quantity,
                "unit_price": str(unit_price),
                "total_price": str(line_total),
            })

        return Response({
            "items": items,
            "subtotal": str(subtotal),
            "total_items": total_items,
        }, status=status.HTTP_200_OK)


class CheckoutCreateOrderView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = CreateOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        cart_items = Cart.objects.select_related("product").filter(user=request.user).order_by("-added_at")
        if not cart_items.exists():
            return Response({"detail": "Cart is empty."}, status=status.HTTP_400_BAD_REQUEST)

        subtotal = Decimal("0.00")
        for c in cart_items:
            if c.product.track_inventory and c.quantity > c.product.stock_quantity:
                return Response(
                    {"detail": f"Insufficient stock for {c.product.name}. Available: {c.product.stock_quantity}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            subtotal += Decimal(str(c.product.final_price)) * Decimal(str(c.quantity))

        shipping_address = data["shipping_address"]
        billing_address = data.get("billing_address") or shipping_address
        payment_method = data["payment_method"]
        currency = data.get("currency", "RWF")
        mobile_money_phone = data.get("mobile_money_phone", "")
        payer_email = data.get("payer_email", "")

        order = Order.objects.create(
            user=request.user,
            total_amount=subtotal,
            status="pending",
            shipping_address=shipping_address,
            billing_address=billing_address,
        )

        for c in cart_items:
            unit_price = Decimal(str(c.product.final_price))
            OrderItem.objects.create(order=order, product=c.product, quantity=c.quantity, price=unit_price)

            if c.product.track_inventory:
                c.product.stock_quantity = max(c.product.stock_quantity - c.quantity, 0)
                if c.product.stock_quantity == 0:
                    c.product.status = "out_of_stock"
                c.product.save(update_fields=["stock_quantity", "status", "updated_at"])

        payment_status = "completed" if payment_method == "bank_transfer" else "pending"
        payment = Payment.objects.create(
            order=order,
            payment_method=payment_method,
            amount=subtotal,
            currency=currency,
            status=payment_status,
            mobile_money_phone=mobile_money_phone,
            payer_email=payer_email,
        )

        cart_items.delete()

        return Response({
            "detail": "Order created successfully.",
            "order": {
                "id": order.id,
                "order_number": order.order_number,
                "status": order.status,
                "total_amount": str(order.total_amount),
                "created_at": order.created_at,
            },
            "payment": {
                "id": payment.id,
                "method": payment.payment_method,
                "status": payment.status,
                "amount": str(payment.amount),
                "currency": payment.currency,
            }
        }, status=status.HTTP_201_CREATED)


# -----------------------------------------------------------------------------
# Orders
# -----------------------------------------------------------------------------
class OrderListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrderListSerializer

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related("items").order_by("-created_at")


class OrderDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = OrderDetailSerializer
    lookup_field = "id"

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related("items", "items__product", "payments")


# -----------------------------------------------------------------------------
# Session -> JWT
# -----------------------------------------------------------------------------
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def session_to_jwt(request):
    refresh = RefreshToken.for_user(request.user)
    return Response({
        "refresh": str(refresh),
        "access": str(refresh.access_token),
        "user": {
            "id": request.user.id,
            "username": request.user.username,
            "email": request.user.email,
        }
    })


@login_required(login_url="/login/")
def mobile_bridge(request):
    refresh = RefreshToken.for_user(request.user)
    return render(request, "mobile_bridge.html", {
        "access_token": str(refresh.access_token),
        "refresh_token": str(refresh),
    })