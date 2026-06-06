"""Fix vendor quotation access - assign Tirth Textile to RFQs"""
import django, os, sys
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
sys.path.insert(0, '.')
django.setup()

from django.utils import timezone
from datetime import timedelta
from procurement.models import User, VendorProfile, RFQ, Notification, ActivityLog

# Get the vendor profile for Tirth
tirth_user = User.objects.get(email='tirth12@gmail.com')
tirth_vendor = tirth_user.vendor_profile
print(f'Vendor: {tirth_vendor.name} (ID: {tirth_vendor.id})')

# 1. Add Tirth Textile to the EXISTING RFQ (Procurement of Office Laptops)
existing_rfq = RFQ.objects.first()
if existing_rfq:
    existing_rfq.assigned_vendors.add(tirth_vendor)
    if existing_rfq.status in ['Compared', 'PO_Generated']:
        # Don't change status of already-processed RFQ
        print(f'Added to existing RFQ: {existing_rfq.rfq_number} (Status: {existing_rfq.status} - already processed)')
    else:
        print(f'Added to existing RFQ: {existing_rfq.rfq_number}')

# 2. Create a FRESH RFQ in "Sent" status assigned to Tirth Textile
officer = User.objects.filter(role='Officer').first()
new_rfq = RFQ.objects.create(
    title='Textile & Fabric Procurement Q2-2026',
    description='Procurement of industrial textiles, fabrics, and work uniforms for Q2. '
                'Vendors are invited to submit competitive pricing and delivery timelines.',
    items=[
        {'name': 'Cotton Work Uniforms', 'spec': 'Size M/L/XL assorted, 100% cotton', 'qty': 50, 'expected_price': 800},
        {'name': 'Heavy Duty Fabric Roll', 'spec': '10m x 1.5m, 300gsm industrial grade', 'qty': 20, 'expected_price': 1500},
        {'name': 'Safety Vest (High-Vis)', 'spec': 'EN 471 Class 2 certified, Yellow', 'qty': 100, 'expected_price': 250},
    ],
    deadline=timezone.now() + timedelta(days=10),
    status='Sent',
    created_by=officer
)
new_rfq.assigned_vendors.add(tirth_vendor)

# 3. Create a second RFQ to give more options
new_rfq2 = RFQ.objects.create(
    title='Office Supplies & Stationery Restock',
    description='Monthly procurement of stationery and office consumables. '
                'Seeking vendors with fast delivery and bulk discount pricing.',
    items=[
        {'name': 'A4 Paper (Box of 5 reams)', 'spec': '80gsm, white, 500 sheets/ream', 'qty': 30, 'expected_price': 1200},
        {'name': 'Ballpoint Pens (Box)', 'spec': 'Blue/Black, 50pcs/box', 'qty': 20, 'expected_price': 180},
        {'name': 'Sticky Notes Pack', 'spec': '76x76mm, assorted colors, 100 sheets', 'qty': 50, 'expected_price': 45},
    ],
    deadline=timezone.now() + timedelta(days=7),
    status='Sent',
    created_by=officer
)
new_rfq2.assigned_vendors.add(tirth_vendor)

# Notify the vendor
Notification.objects.create(
    user=tirth_user,
    title='New RFQ Invitation',
    message=f'You have been invited to submit a quotation for: {new_rfq.rfq_number} - {new_rfq.title}'
)
Notification.objects.create(
    user=tirth_user,
    title='New RFQ Invitation',
    message=f'You have been invited to submit a quotation for: {new_rfq2.rfq_number} - {new_rfq2.title}'
)

ActivityLog.objects.create(
    user=officer,
    action='RFQ Published',
    details=f'Published {new_rfq.rfq_number} and assigned to {tirth_vendor.name}'
)
ActivityLog.objects.create(
    user=officer,
    action='RFQ Published',
    details=f'Published {new_rfq2.rfq_number} and assigned to {tirth_vendor.name}'
)

print(f'Created new RFQ: {new_rfq.rfq_number} - {new_rfq.title}')
print(f'Created new RFQ: {new_rfq2.rfq_number} - {new_rfq2.title}')
print(f'Both assigned to vendor: {tirth_vendor.name}')
print()
print('=== VERIFICATION ===')
from procurement.models import RFQ as RFQ2
active_rfqs = RFQ2.objects.filter(assigned_vendors=tirth_vendor, status__in=['Sent', 'Received'])
print(f'Active RFQ invitations for Tirth Textile: {active_rfqs.count()}')
for r in active_rfqs:
    print(f'  - {r.rfq_number}: {r.title} | Deadline: {r.deadline.strftime("%Y-%m-%d")} | Items: {len(r.items)}')
print()
print('DONE! Tirth can now see active RFQ invitations on the Quotations page.')
