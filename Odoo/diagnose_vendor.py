"""Diagnose Vendor quotation access issue"""
import django, os, sys
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
sys.path.insert(0, '.')
django.setup()

from procurement.models import User, VendorProfile, RFQ, Quotation

print('=== VENDOR USERS ===')
for u in User.objects.filter(role='Vendor'):
    print(f'  User: {u.email} ({u.first_name} {u.last_name})')
    # Check if linked to VendorProfile
    try:
        vp = u.vendor_profile
        print(f'    -> Linked VendorProfile: {vp.name} (ID:{vp.id}) Status:{vp.status}')
        # Check assigned RFQs
        rfqs = RFQ.objects.filter(assigned_vendors=vp)
        print(f'    -> Assigned RFQs: {rfqs.count()}')
        for r in rfqs:
            print(f'       - {r.rfq_number}: {r.title} | Status: {r.status}')
        # Check quotations submitted
        quotes = Quotation.objects.filter(vendor=vp)
        print(f'    -> Quotations submitted: {quotes.count()}')
    except Exception as e:
        print(f'    -> NO VendorProfile linked! ({e})')

print()
print('=== ALL VENDOR PROFILES ===')
for vp in VendorProfile.objects.all():
    linked_user = vp.user if hasattr(vp, 'user') and vp.user else None
    print(f'  {vp.name} | User: {linked_user.email if linked_user else "NO USER LINKED"} | Status: {vp.status}')

print()
print('=== ALL RFQs & ASSIGNED VENDORS ===')
for r in RFQ.objects.all():
    vendors = list(r.assigned_vendors.values_list('name', flat=True))
    print(f'  {r.rfq_number}: {r.title[:40]} | Status: {r.status} | Vendors: {vendors}')
