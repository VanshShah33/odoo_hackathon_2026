import random
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from datetime import timedelta

from procurement.models import (
    VendorProfile, RFQ, Quotation, Approval, PurchaseOrder, Invoice, ActivityLog, Notification
)

User = get_user_model()

class Command(BaseCommand):
    help = 'Seeds the database with realistic initial data for the procurement ERP'

    def handle(self, *args, **kwargs):
        self.stdout.write("Clearing existing data...")
        Invoice.objects.all().delete()
        PurchaseOrder.objects.all().delete()
        Approval.objects.all().delete()
        Quotation.objects.all().delete()
        RFQ.objects.all().delete()
        VendorProfile.objects.all().delete()
        Notification.objects.all().delete()
        ActivityLog.objects.all().delete()
        User.objects.all().delete()

        self.stdout.write("Creating Users...")
        # Create standard passwords
        password = "password123"

        # Procurement Officer
        officer = User.objects.create_user(
            email="officer@vendorbridge.com",
            first_name="Harsh",
            last_name="Mehta",
            role="Officer"
        )
        officer.set_password(password)
        officer.save()

        # Manager
        manager = User.objects.create_user(
            email="manager@vendorbridge.com",
            first_name="Sanjay",
            last_name="Sharma",
            role="Manager"
        )
        manager.set_password(password)
        manager.save()

        # Admin
        admin = User.objects.create_superuser(
            email="admin@vendorbridge.com",
            first_name="Admin",
            last_name="User",
            role="Admin"
        )
        admin.set_password(password)
        admin.save()

        # Vendor Users
        vendor_user_1 = User.objects.create_user(email="nexgen@vendorbridge.com", first_name="Rajesh", last_name="Kumar", role="Vendor")
        vendor_user_1.set_password(password)
        vendor_user_1.save()

        vendor_user_2 = User.objects.create_user(email="primeoffice@vendorbridge.com", first_name="Anil", last_name="Gupta", role="Vendor")
        vendor_user_2.set_password(password)
        vendor_user_2.save()

        vendor_user_3 = User.objects.create_user(email="logistics@vendorbridge.com", first_name="Vikram", last_name="Singh", role="Vendor")
        vendor_user_3.set_password(password)
        vendor_user_3.save()

        vendor_user_4 = User.objects.create_user(email="apex@vendorbridge.com", first_name="Karan", last_name="Joshi", role="Vendor")
        vendor_user_4.set_password(password)
        vendor_user_4.save()

        self.stdout.write("Creating Vendor Profiles...")
        # 1. NexGen Tech
        v1 = VendorProfile.objects.create(
            user=vendor_user_1,
            name="NexGen Technologies Ltd",
            category="IT Hardware",
            gst_number="27AAAAA1234A1Z1",
            contact_email="sales@nexgentech.com",
            phone="+919876543210",
            address="Building B, Tech Park, Pune - 411001",
            rating=4.8,
            status="Active",
            contact_person="Rajesh Kumar",
            risk_score=10,
            is_ai_recommended=True
        )
        
        # 2. Prime Office Solutions
        v2 = VendorProfile.objects.create(
            user=vendor_user_2,
            name="Prime Office Solutions",
            category="Office Supplies",
            gst_number="27BBBBB5678B1Z2",
            contact_email="orders@primeoffice.in",
            phone="+919822334455",
            address="Plot 42, Industrial Area, Mumbai - 400072",
            rating=4.2,
            status="Active",
            contact_person="Anil Gupta",
            risk_score=18,
            is_ai_recommended=False
        )

        # 3. Global Logistics Ltd
        v3 = VendorProfile.objects.create(
            user=vendor_user_3,
            name="Global Logistics Ltd",
            category="Services & Logistics",
            gst_number="27CCCCC9012C1Z3",
            contact_email="support@globallogistics.com",
            phone="+912288776655",
            address="Cargo Hub 3, Airport Road, Delhi - 110037",
            rating=4.5,
            status="Active",
            contact_person="Vikram Singh",
            risk_score=15,
            is_ai_recommended=True
        )

        # 4. Apex Construction & Facilities
        v4 = VendorProfile.objects.create(
            user=vendor_user_4,
            name="Apex Construction & Facilities",
            category="Facilities & Work",
            gst_number="27DDDDD3456D1Z4",
            contact_email="projects@apexfacilities.com",
            phone="+919911223344",
            address="Civic Center, Ring Road, Bangalore - 560001",
            rating=3.9,
            status="Under Review",
            contact_person="Karan Joshi",
            risk_score=35,
            is_ai_recommended=False
        )

        all_vendors = [v1, v2, v3, v4]

        # Log User Registration activities
        ActivityLog.objects.create(user=officer, action="Account Seeded", details="Procurement Officer seeded.")
        ActivityLog.objects.create(user=manager, action="Account Seeded", details="Manager account seeded.")
        ActivityLog.objects.create(user=admin, action="Account Seeded", details="System Admin account seeded.")
        
        for v in all_vendors:
            ActivityLog.objects.create(user=v.user, action="Vendor Created", details=f"Registered vendor company: {v.name}")

        self.stdout.write("Creating Historical RFQs, Quotations, POs, and Invoices...")
        # Create Historical Data spread across the last 4 months
        now = timezone.now()

        # --- TRANSACTION 1 (4 months ago: Completed IT Hardware Purchase) ---
        t1_date = now - timedelta(days=120)
        rfq1 = RFQ.objects.create(
            title="Office Laptops Upgrade",
            description="Procurement of 10 high-performance laptops for engineering team.",
            items=[
                {"name": "Developer Laptop", "spec": "16GB RAM, 512GB SSD, Intel i7", "qty": 10, "expected_price": 1000}
            ],
            deadline=t1_date + timedelta(days=7),
            status="PO_Generated",
            created_by=officer
        )
        rfq1.created_at = t1_date
        rfq1.save()
        rfq1.assigned_vendors.add(v1)

        # Quotes for RFQ 1
        q1_v1 = Quotation.objects.create(
            rfq=rfq1,
            vendor=v1,
            delivery_timeline_days=5,
            items_quotation=[
                {"name": "Developer Laptop", "spec": "16GB RAM, 512GB SSD, Intel i7", "qty": 10, "unit_price": 950}
            ],
            notes="Offering a discount on bulk upgrade.",
            status="Approved"
        )
        q1_v1.created_at = t1_date + timedelta(days=2)
        q1_v1.save()

        # Approval
        app1 = Approval.objects.create(
            quotation=q1_v1,
            approver=manager,
            status="Approved",
            remarks="Lowest bid matches all specs. Approved."
        )
        app1.created_at = t1_date + timedelta(days=3)
        app1.save()

        # Purchase Order
        po1 = PurchaseOrder.objects.create(
            quotation=q1_v1,
            status="Invoiced",
            timeline_status="Invoiced",
            expected_delivery_date=t1_date + timedelta(days=5),
            savings_amount=500.00,
            savings_percentage=5.0,
            risk_score=8
        )
        po1.created_at = t1_date + timedelta(days=4)
        po1.save()

        # Invoice
        inv1 = Invoice.objects.create(
            purchase_order=po1,
            status="Paid"
        )
        inv1.created_at = t1_date + timedelta(days=10)
        inv1.save()


        # --- TRANSACTION 2 (3 months ago: Completed Services & Logistics Purchase) ---
        t2_date = now - timedelta(days=90)
        rfq2 = RFQ.objects.create(
            title="Warehouse Shifting Services",
            description="End-to-end relocation services for Pune warehouse to Mumbai depot.",
            items=[
                {"name": "Warehouse Shifting Service", "spec": "Pack, transport, and unpack inventory", "qty": 1, "expected_price": 5000}
            ],
            deadline=t2_date + timedelta(days=5),
            status="PO_Generated",
            created_by=officer
        )
        rfq2.created_at = t2_date
        rfq2.save()
        rfq2.assigned_vendors.add(v3)

        # Quotes
        q2_v3 = Quotation.objects.create(
            rfq=rfq2,
            vendor=v3,
            delivery_timeline_days=3,
            items_quotation=[
                {"name": "Warehouse Shifting Service", "spec": "Pack, transport, and unpack inventory", "qty": 1, "unit_price": 4800}
            ],
            notes="Includes comprehensive transit insurance.",
            status="Approved"
        )
        q2_v3.created_at = t2_date + timedelta(days=1)
        q2_v3.save()

        app2 = Approval.objects.create(
            quotation=q2_v3,
            approver=manager,
            status="Approved",
            remarks="Logistics partner has excellent ratings. Approved."
        )
        app2.created_at = t2_date + timedelta(days=2)
        app2.save()

        po2 = PurchaseOrder.objects.create(
            quotation=q2_v3,
            status="Invoiced",
            timeline_status="Invoiced",
            expected_delivery_date=t2_date + timedelta(days=3),
            savings_amount=200.00,
            savings_percentage=4.0,
            risk_score=10
        )
        po2.created_at = t2_date + timedelta(days=3)
        po2.save()

        inv2 = Invoice.objects.create(
            purchase_order=po2,
            status="Paid"
        )
        inv2.created_at = t2_date + timedelta(days=5)
        inv2.save()


        # --- TRANSACTION 3 (2 months ago: Office Supplies Purchase) ---
        t3_date = now - timedelta(days=60)
        rfq3 = RFQ.objects.create(
            title="Bulk Stationery and Office Cabinets",
            description="Yearly supply of registers, pens, and files, along with 4 office steel cabinets.",
            items=[
                {"name": "Office Stationery Kit", "spec": "Assorted standard office stationery", "qty": 50, "expected_price": 20},
                {"name": "Steel Cabinets", "spec": "4-Drawer Lockable Steel Cabinet", "qty": 4, "expected_price": 300}
            ],
            deadline=t3_date + timedelta(days=10),
            status="PO_Generated",
            created_by=officer
        )
        rfq3.created_at = t3_date
        rfq3.save()
        rfq3.assigned_vendors.add(v2)

        # Quotes
        q3_v2 = Quotation.objects.create(
            rfq=rfq3,
            vendor=v2,
            delivery_timeline_days=7,
            items_quotation=[
                {"name": "Office Stationery Kit", "spec": "Assorted standard office stationery", "qty": 50, "unit_price": 18},
                {"name": "Steel Cabinets", "spec": "4-Drawer Lockable Steel Cabinet", "qty": 4, "unit_price": 280}
            ],
            notes="Free shipping included.",
            status="Approved"
        )
        q3_v2.created_at = t3_date + timedelta(days=3)
        q3_v2.save()

        app3 = Approval.objects.create(
            quotation=q3_v2,
            approver=manager,
            status="Approved",
            remarks="Prices are lower than retail market standards."
        )
        app3.created_at = t3_date + timedelta(days=4)
        app3.save()

        po3 = PurchaseOrder.objects.create(
            quotation=q3_v2,
            status="Invoiced",
            timeline_status="Invoiced",
            expected_delivery_date=t3_date + timedelta(days=7),
            savings_amount=180.00,
            savings_percentage=9.0,
            risk_score=12
        )
        po3.created_at = t3_date + timedelta(days=5)
        po3.save()

        inv3 = Invoice.objects.create(
            purchase_order=po3,
            status="Posted"  # Outstanding invoice, unpaid
        )
        inv3.created_at = t3_date + timedelta(days=7)
        inv3.save()


        # --- TRANSACTION 4 (1 month ago: IT Hardware Purchase) ---
        t4_date = now - timedelta(days=30)
        rfq4 = RFQ.objects.create(
            title="Server UPS Replacement",
            description="Procurement of double conversion online UPS for server room backup.",
            items=[
                {"name": "Online UPS 10kVA", "spec": "Double conversion, 1hr backup battery rack", "qty": 1, "expected_price": 2000}
            ],
            deadline=t4_date + timedelta(days=6),
            status="PO_Generated",
            created_by=officer
        )
        rfq4.created_at = t4_date
        rfq4.save()
        rfq4.assigned_vendors.add(v1)

        # Quotes
        q4_v1 = Quotation.objects.create(
            rfq=rfq4,
            vendor=v1,
            delivery_timeline_days=8,
            items_quotation=[
                {"name": "Online UPS 10kVA", "spec": "Double conversion, 1hr backup battery rack", "qty": 1, "unit_price": 2100}
            ],
            notes="3-year onsite warranty included.",
            status="Approved"
        )
        q4_v1.created_at = t4_date + timedelta(days=2)
        q4_v1.save()

        app4 = Approval.objects.create(
            quotation=q4_v1,
            approver=manager,
            status="Approved",
            remarks="Critical infrastructure. Approved."
        )
        app4.created_at = t4_date + timedelta(days=3)
        app4.save()

        po4 = PurchaseOrder.objects.create(
            quotation=q4_v1,
            status="Invoiced",
            timeline_status="Invoiced",
            expected_delivery_date=t4_date + timedelta(days=8),
            savings_amount=100.00,
            savings_percentage=4.5,
            risk_score=9
        )
        po4.created_at = t4_date + timedelta(days=4)
        po4.save()

        inv4 = Invoice.objects.create(
            purchase_order=po4,
            status="Posted"  # Outstanding invoice, unpaid
        )
        inv4.created_at = t4_date + timedelta(days=5)
        inv4.save()


        # --- ACTIVE / RUNNING FLOWS (Pending Approvals & RFQs) ---

        # 1. RFQ pending comparison
        rfq_active_1 = RFQ.objects.create(
            title="Office Cafeteria Coffee Maker",
            description="Procurement of an industrial espresso machine for employees cafeteria.",
            items=[
                {"name": "Espresso Machine", "spec": "Dual group head, automatic steam wand", "qty": 1, "expected_price": 1500}
            ],
            deadline=now + timedelta(days=5),
            status="Received",
            created_by=officer
        )
        rfq_active_1.assigned_vendors.add(v1)
        rfq_active_1.assigned_vendors.add(v2)

        # Submitted bids
        q_act1_v1 = Quotation.objects.create(
            rfq=rfq_active_1,
            vendor=v1,
            delivery_timeline_days=6,
            items_quotation=[
                {"name": "Espresso Machine", "spec": "Dual group head, automatic steam wand", "qty": 1, "unit_price": 1450}
            ],
            notes="Italian build machine.",
            status="Submitted"
        )
        
        q_act1_v2 = Quotation.objects.create(
            rfq=rfq_active_1,
            vendor=v2,
            delivery_timeline_days=4,
            items_quotation=[
                {"name": "Espresso Machine", "spec": "Dual group head, automatic steam wand", "qty": 1, "unit_price": 1390}
            ],
            notes="Includes free training and starter coffee beans.",
            status="Submitted"
        )

        # 2. Quotation Submitted for Approval (Pending Approval)
        rfq_active_2 = RFQ.objects.create(
            title="Workstation Chairs",
            description="Standard ergonomic mesh back chairs with armrests.",
            items=[
                {"name": "Ergonomic Mesh Chair", "spec": "Adjustable lumbar support and armrests", "qty": 15, "expected_price": 120}
            ],
            deadline=now + timedelta(days=3),
            status="Compared",
            created_by=officer
        )
        rfq_active_2.assigned_vendors.add(v2)

        q_act2_v2 = Quotation.objects.create(
            rfq=rfq_active_2,
            vendor=v2,
            delivery_timeline_days=5,
            items_quotation=[
                {"name": "Ergonomic Mesh Chair", "spec": "Adjustable lumbar support and armrests", "qty": 15, "unit_price": 110}
            ],
            notes="Prime ergonomic series.",
            status="Shortlisted"
        )

        app_pending = Approval.objects.create(
            quotation=q_act2_v2,
            approver=manager,
            status="Pending"
        )

        # 3. Draft RFQ
        rfq_draft = RFQ.objects.create(
            title="IT Server Room Racks",
            description="Procurement of two 42U Server Racks with cable managers.",
            items=[
                {"name": "42U Server Rack", "spec": "600x1000mm with fans and PDUs", "qty": 2, "expected_price": 400}
            ],
            deadline=now + timedelta(days=10),
            status="Draft",
            created_by=officer
        )
        rfq_draft.assigned_vendors.add(v1)

        # Create some random notifications
        Notification.objects.create(
            user=officer,
            title="Welcome to VendorBridge",
            message="Welcome! Your procurement system is ready. You can create RFQs, manage vendors, and generate reports."
        )
        Notification.objects.create(
            user=manager,
            title="Pending Approvals",
            message="You have a new approval request for Workstation Chairs. Please review."
        )

        # Done seeding!
        self.stdout.write(self.style.SUCCESS('Successfully seeded database with realistic ERP data!'))
        self.stdout.write(f"Seed Summary:")
        self.stdout.write(f"- Users: {User.objects.count()}")
        self.stdout.write(f"- Vendors: {VendorProfile.objects.count()}")
        self.stdout.write(f"- RFQs: {RFQ.objects.count()}")
        self.stdout.write(f"- Quotations: {Quotation.objects.count()}")
        self.stdout.write(f"- POs: {PurchaseOrder.objects.count()}")
        self.stdout.write(f"- Invoices: {Invoice.objects.count()}")
