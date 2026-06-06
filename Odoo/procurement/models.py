from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, username=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'Admin')
        return self.create_user(email, password, **extra_fields)

class User(AbstractUser):
    ROLE_CHOICES = (
        ('Officer', 'Procurement Officer'),
        ('Vendor', 'Vendor'),
        ('Manager', 'Manager / Approver'),
        ('Admin', 'Admin'),
    )
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='Officer')
    
    objects = UserManager()
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    
    def __str__(self):
        return f"{self.email} ({self.role})"

class VendorProfile(models.Model):
    STATUS_CHOICES = (
        ('Active', 'Active'),
        ('Suspended', 'Suspended'),
        ('Under Review', 'Under Review'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='vendor_profile', null=True, blank=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=100) # e.g. IT Hardware, Office Supplies, Services
    gst_number = models.CharField(max_length=15, unique=True)
    contact_email = models.EmailField()
    phone = models.CharField(max_length=15)
    address = models.TextField()
    rating = models.FloatField(default=5.0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Active')
    contact_person = models.CharField(max_length=100, default="John Doe")
    risk_score = models.IntegerField(default=15)
    is_ai_recommended = models.BooleanField(default=False)
    
    @property
    def total_orders(self):
        return PurchaseOrder.objects.filter(quotation__vendor=self).count()

    @property
    def total_procurement_value(self):
        from django.db.models import Sum
        val = Invoice.objects.filter(purchase_order__quotation__vendor=self).aggregate(Sum('total_amount'))['total_amount__sum']
        return float(val) if val else 0.0

    @property
    def rfqs_participated(self):
        return self.assigned_rfqs.count()

    @property
    def quotations_submitted(self):
        return self.quotations.count()

    @property
    def approval_rate(self):
        total = self.quotations.count()
        if total == 0:
            return 100.0
        approved = self.quotations.filter(status='Approved').count()
        return round((approved / total) * 100.0, 1)

    @property
    def cost_saving_percentage(self):
        total_exp = 0.0
        total_bid = 0.0
        for q in self.quotations.all():
            for item in q.rfq.items:
                total_exp += float(item.get('qty', 1)) * float(item.get('expected_price', 100))
            total_bid += float(q.subtotal)
        if total_exp == 0 or total_bid >= total_exp:
            return 15.0
        return round(((total_exp - total_bid) / total_exp) * 100.0, 1)
    
    def __str__(self):
        return self.name

class RFQ(models.Model):
    STATUS_CHOICES = (
        ('Draft', 'Draft'),
        ('Sent', 'Sent'),
        ('Received', 'Quotations Received'),
        ('Compared', 'Compared'),
        ('Approved', 'Approved'),
        ('PO_Generated', 'PO Generated'),
        ('Cancelled', 'Cancelled'),
    )
    rfq_number = models.CharField(max_length=50, unique=True, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    items = models.JSONField()  # Array of objects: [{name, spec, qty}]
    deadline = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_rfqs')
    assigned_vendors = models.ManyToManyField(VendorProfile, related_name='assigned_rfqs')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.rfq_number:
            last_rfq = RFQ.objects.all().order_by('id').last()
            if last_rfq:
                last_id = last_rfq.id
            else:
                last_id = 0
            self.rfq_number = f"RFQ/2026/{last_id + 1:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.rfq_number} - {self.title}"

class Quotation(models.Model):
    STATUS_CHOICES = (
        ('Draft', 'Draft'),
        ('Submitted', 'Submitted'),
        ('Shortlisted', 'Shortlisted'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    )
    rfq = models.ForeignKey(RFQ, on_delete=models.CASCADE, related_name='quotations')
    vendor = models.ForeignKey(VendorProfile, on_delete=models.CASCADE, related_name='quotations')
    delivery_timeline_days = models.IntegerField(default=7)
    items_quotation = models.JSONField() # Array of objects: [{name, spec, qty, unit_price}]
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Draft')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        sub = 0.0
        for item in self.items_quotation:
            qty = float(item.get('qty', 0))
            price = float(item.get('unit_price', 0))
            sub += qty * price
        self.subtotal = sub
        # Standard GST: 18%
        self.tax_amount = sub * 0.18
        self.total_price = self.subtotal + self.tax_amount
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Quote from {self.vendor.name} for {self.rfq.rfq_number}"

class Approval(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    )
    quotation = models.ForeignKey(Quotation, on_delete=models.CASCADE, related_name='approvals')
    approver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='approvals_done')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Approval for {self.quotation.rfq.rfq_number} - {self.status}"

class PurchaseOrder(models.Model):
    STATUS_CHOICES = (
        ('Draft', 'Draft'),
        ('Confirmed', 'Confirmed'),
        ('Shipped', 'Shipped'),
        ('Received', 'Received'),
        ('Invoiced', 'Invoiced'),
    )
    po_number = models.CharField(max_length=50, unique=True, editable=False)
    quotation = models.OneToOneField(Quotation, on_delete=models.CASCADE, related_name='purchase_order')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Confirmed')
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Advanced timeline & savings metrics
    expected_delivery_date = models.DateField(null=True, blank=True)
    savings_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    savings_percentage = models.FloatField(default=0.0)
    risk_score = models.IntegerField(default=10)
    timeline_status = models.CharField(max_length=50, default='Confirmed') # Confirmed -> Shipped -> Received -> Invoiced

    @property
    def vendor_performance_score(self):
        return int(self.quotation.vendor.rating * 20)

    @property
    def vendor_rank(self):
        rfq = self.quotation.rfq
        quotes = list(rfq.quotations.all().order_by('total_price'))
        try:
            rank = quotes.index(self.quotation) + 1
            return f"Rank #{rank}"
        except ValueError:
            return "Rank #1"

    @property
    def approval_reference(self):
        approval = self.quotation.approvals.filter(status='Approved').first()
        if approval:
            return f"APP-{approval.id:04d}"
        return "APP-SYSTEM"

    @property
    def quotation_reference(self):
        return f"QT-{self.quotation.id:04d}"

    @property
    def procurement_savings_amount(self):
        rfq = self.quotation.rfq
        expected_total = sum(float(item.get('qty', 1)) * float(item.get('expected_price', 100)) for item in rfq.items)
        savings = expected_total - float(self.quotation.total_price)
        return max(0.0, savings)

    @property
    def procurement_savings_percentage(self):
        rfq = self.quotation.rfq
        expected_total = sum(float(item.get('qty', 1)) * float(item.get('expected_price', 100)) for item in rfq.items)
        if expected_total == 0:
            return 0.0
        pct = (expected_total - float(self.quotation.total_price)) / expected_total * 100.0
        return round(max(0.0, pct), 1)

    def save(self, *args, **kwargs):
        if not self.po_number:
            last_po = PurchaseOrder.objects.all().order_by('id').last()
            if last_po:
                last_id = last_po.id
            else:
                last_id = 0
            self.po_number = f"PO/2026/{last_id + 1:04d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.po_number

class Invoice(models.Model):
    STATUS_CHOICES = (
        ('Draft', 'Draft'),
        ('Posted', 'Posted'),
        ('Paid', 'Paid'),
        ('Cancelled', 'Cancelled'),
    )
    invoice_number = models.CharField(max_length=50, unique=True, editable=False)
    purchase_order = models.OneToOneField(PurchaseOrder, on_delete=models.CASCADE, related_name='invoice')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Posted')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            last_inv = Invoice.objects.all().order_by('id').last()
            if last_inv:
                last_id = last_inv.id
            else:
                last_id = 0
            self.invoice_number = f"INV-2026-{last_id + 1:04d}"
        
        self.subtotal = self.purchase_order.quotation.subtotal
        self.tax_amount = self.purchase_order.quotation.tax_amount
        self.total_amount = self.purchase_order.quotation.total_price
        super().save(*args, **kwargs)

    def __str__(self):
        return self.invoice_number

class ActivityLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities', null=True, blank=True)
    action = models.CharField(max_length=255)
    details = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.timestamp} - {self.action}"

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    read = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.email} - {self.title} - Read: {self.read}"
