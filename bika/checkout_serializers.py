from rest_framework import serializers


class CheckoutPreviewItemSerializer(serializers.Serializer):
    cart_item_id = serializers.IntegerField()
    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    quantity = serializers.IntegerField()
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2)


class CheckoutPreviewSerializer(serializers.Serializer):
    items = CheckoutPreviewItemSerializer(many=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_items = serializers.IntegerField()


class CreateOrderSerializer(serializers.Serializer):
    shipping_address = serializers.CharField()
    billing_address = serializers.CharField(required=False, allow_blank=True)
    payment_method = serializers.CharField()
    currency = serializers.CharField(required=False, default="RWF")
    mobile_money_phone = serializers.CharField(required=False, allow_blank=True)
    payer_email = serializers.EmailField(required=False, allow_blank=True)

    def validate_payment_method(self, value):
        allowed = {
            "mtn_rw", "airtel_rw",
            "mpesa", "tigo_tz", "airtel_tz", "halotel_tz",
            "mtn_ug", "airtel_ug", "mpesa_ke",
            "visa", "mastercard", "amex", "paypal", "bank_transfer",
        }
        if value not in allowed:
            raise serializers.ValidationError("Unsupported payment_method.")
        return value
from rest_framework import serializers


class CheckoutPreviewItemSerializer(serializers.Serializer):
    cart_item_id = serializers.IntegerField()
    product_id = serializers.IntegerField()
    product_name = serializers.CharField()
    quantity = serializers.IntegerField()
    unit_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2)


class CheckoutPreviewSerializer(serializers.Serializer):
    items = CheckoutPreviewItemSerializer(many=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_items = serializers.IntegerField()


class CreateOrderSerializer(serializers.Serializer):
    shipping_address = serializers.CharField()
    billing_address = serializers.CharField(required=False, allow_blank=True)
    payment_method = serializers.CharField()
    currency = serializers.CharField(required=False, default="RWF")
    mobile_money_phone = serializers.CharField(required=False, allow_blank=True)
    payer_email = serializers.EmailField(required=False, allow_blank=True)

    def validate_payment_method(self, value):
        allowed = {
            "mtn_rw", "airtel_rw",
            "mpesa", "tigo_tz", "airtel_tz", "halotel_tz",
            "mtn_ug", "airtel_ug", "mpesa_ke",
            "visa", "mastercard", "amex", "paypal", "bank_transfer",
        }
        if value not in allowed:
            raise serializers.ValidationError("Unsupported payment_method.")
        return value
