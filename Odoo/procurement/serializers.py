from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import VendorProfile, RFQ, Quotation, Approval, PurchaseOrder, Invoice, ActivityLog, Notification

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ['id', 'email', 'role', 'first_name', 'last_name', 'username', 'password']

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User.objects.create_user(
            email=validated_data['email'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
            role=validated_data.get('role', 'Officer')
        )
        if password:
            user.set_password(password)
            user.save()
        return user

class VendorProfileSerializer(serializers.ModelSerializer):
    total_orders = serializers.SerializerMethodField()
    total_procurement_value = serializers.SerializerMethodField()
    rfqs_participated = serializers.SerializerMethodField()
    quotations_submitted = serializers.SerializerMethodField()
    approval_rate = serializers.SerializerMethodField()

    class Meta:
        model = VendorProfile
        fields = '__all__'

    def get_total_orders(self, obj):
        return PurchaseOrder.objects.filter(quotation__vendor=obj).count()

    def get_total_procurement_value(self, obj):
        from django.db.models import Sum
        val = Invoice.objects.filter(purchase_order__quotation__vendor=obj).aggregate(Sum('total_amount'))['total_amount__sum']
        return float(val) if val else 0.0

    def get_rfqs_participated(self, obj):
        return obj.assigned_rfqs.count()

    def get_quotations_submitted(self, obj):
        return obj.quotations.count()

    def get_approval_rate(self, obj):
        total = obj.quotations.count()
        if total == 0:
            return 100.0
        approved = obj.quotations.filter(status='Approved').count()
        return round((approved / total) * 100.0, 1)

class RFQSerializer(serializers.ModelSerializer):
    assigned_vendors_details = VendorProfileSerializer(source='assigned_vendors', many=True, read_only=True)
    created_by_email = serializers.EmailField(source='created_by.email', read_only=True)

    class Meta:
        model = RFQ
        fields = '__all__'

class QuotationSerializer(serializers.ModelSerializer):
    vendor_details = VendorProfileSerializer(source='vendor', read_only=True)
    rfq_number = serializers.CharField(source='rfq.rfq_number', read_only=True)
    rfq_title = serializers.CharField(source='rfq.title', read_only=True)

    class Meta:
        model = Quotation
        fields = '__all__'

class ApprovalSerializer(serializers.ModelSerializer):
    approver_email = serializers.EmailField(source='approver.email', read_only=True)
    quotation_vendor_name = serializers.CharField(source='quotation.vendor.name', read_only=True)
    rfq_number = serializers.CharField(source='quotation.rfq.rfq_number', read_only=True)

    class Meta:
        model = Approval
        fields = '__all__'

class PurchaseOrderSerializer(serializers.ModelSerializer):
    quotation_details = QuotationSerializer(source='quotation', read_only=True)
    rfq_number = serializers.CharField(source='quotation.rfq.rfq_number', read_only=True)
    vendor_name = serializers.CharField(source='quotation.vendor.name', read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = '__all__'

class InvoiceSerializer(serializers.ModelSerializer):
    purchase_order_number = serializers.CharField(source='purchase_order.po_number', read_only=True)
    vendor_name = serializers.CharField(source='purchase_order.quotation.vendor.name', read_only=True)
    rfq_number = serializers.CharField(source='purchase_order.quotation.rfq.rfq_number', read_only=True)

    class Meta:
        model = Invoice
        fields = '__all__'

class ActivityLogSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True, allow_null=True)

    class Meta:
        model = ActivityLog
        fields = '__all__'

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
