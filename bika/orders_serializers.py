from rest_framework import serializers
from .models import Order, OrderItem, Payment


class OrderItemMiniSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    total_price = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            "id",
            "product",
            "product_name",
            "quantity",
            "price",
            "total_price",
        ]

    def get_total_price(self, obj):
        return str(obj.total_price)


class PaymentMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "payment_method",
            "amount",
            "currency",
            "status",
            "transaction_id",
            "created_at",
            "paid_at",
        ]


class OrderListSerializer(serializers.ModelSerializer):
    items_count = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "total_amount",
            "status",
            "created_at",
            "items_count",
        ]

    def get_items_count(self, obj):
        return obj.items.count()


class OrderDetailSerializer(serializers.ModelSerializer):
    items = OrderItemMiniSerializer(many=True, read_only=True)
    payments = PaymentMiniSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "total_amount",
            "status",
            "shipping_address",
            "billing_address",
            "created_at",
            "updated_at",
            "items",
            "payments",
        ]
