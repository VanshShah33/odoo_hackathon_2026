from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from procurement.models import VendorProfile, RFQ, Quotation, Approval, PurchaseOrder, Invoice

User = get_user_model()

class ProcurementWorkflowTests(TestCase):
    def setUp(self):
        # 1. Setup Roles
        self.officer = User.objects.create_user(
            email="officer_test@vendorbridge.com",
            first_name="Officer",
            last_name="Test",
            role="Officer"
        )
        self.manager = User.objects.create_user(
            email="manager_test@vendorbridge.com",
            first_name="Manager",
            last_name="Test",
            role="Manager"
        )
        self.vendor_user = User.objects.create_user(
            email="vendor_test@vendorbridge.com",
            first_name="Vendor",
            last_name="Test",
            role="Vendor"
        )

        # 2. Create Vendor Profile
        self.vendor_profile = VendorProfile.objects.create(
            user=self.vendor_user,
            name="Test Vendor Ltd",
            category="IT Hardware",
            gst_number="27AAAAA9999A1Z1",
            contact_email="test@vendor.com",
            phone="1234567890",
            address="Test Address",
            status="Active"
        )

    def test_user_roles(self):
        self.assertEqual(self.officer.role, "Officer")
        self.assertEqual(self.manager.role, "Manager")
        self.assertEqual(self.vendor_user.role, "Vendor")
        self.assertEqual(self.vendor_user.vendor_profile.name, "Test Vendor Ltd")

    def test_rfq_workflow(self):
        # Create RFQ in Draft status
        rfq = RFQ.objects.create(
            title="Test Procurement",
            description="Test Description",
            items=[{"name": "Laptop", "spec": "16GB", "qty": 5, "expected_price": 500}],
            deadline=timezone.now() + timedelta(days=2),
            status="Draft",
            created_by=self.officer
        )
        rfq.assigned_vendors.add(self.vendor_profile)

        # Assert RFQ number generated and status is Draft
        self.assertTrue(rfq.rfq_number.startswith("RFQ/"))
        self.assertEqual(rfq.status, "Draft")

        # Create Quotation (submitted by vendor)
        quote = Quotation.objects.create(
            rfq=rfq,
            vendor=self.vendor_profile,
            delivery_timeline_days=4,
            items_quotation=[{"name": "Laptop", "spec": "16GB", "qty": 5, "unit_price": 450}],
            notes="Vendor remarks",
            status="Submitted"
        )

        # Verify GST (18% tax) and totals
        self.assertEqual(float(quote.subtotal), 5 * 450)
        self.assertEqual(float(quote.tax_amount), (5 * 450) * 0.18)
        self.assertEqual(float(quote.total_price), (5 * 450) * 1.18)

        # Setup Approval request
        approval = Approval.objects.create(
            quotation=quote,
            approver=self.manager,
            status="Pending"
        )
        self.assertEqual(approval.status, "Pending")

        # Approve quotation
        quote.status = "Approved"
        quote.save()
        approval.status = "Approved"
        approval.remarks = "Approved by Manager"
        approval.save()
        rfq.status = "Approved"
        rfq.save()

        self.assertEqual(quote.status, "Approved")
        self.assertEqual(rfq.status, "Approved")

        # Create Purchase Order
        po = PurchaseOrder.objects.create(
            quotation=quote,
            status="Confirmed"
        )
        self.assertTrue(po.po_number.startswith("PO/"))

        # Create Invoice
        invoice = Invoice.objects.create(
            purchase_order=po,
            status="Posted"
        )
        self.assertTrue(invoice.invoice_number.startswith("INV-"))
        self.assertEqual(invoice.total_amount, quote.total_price)


class SettingsWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="settings_user@vendorbridge.com",
            password="oldpassword123",
            first_name="Settings",
            last_name="User",
            role="Officer"
        )

    def test_settings_page_requires_login(self):
        response = self.client.get('/settings/')
        self.assertEqual(response.status_code, 302)

    def test_settings_page_with_login(self):
        self.client.force_login(self.user)
        response = self.client.get('/settings/')
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'procurement/settings.html')
