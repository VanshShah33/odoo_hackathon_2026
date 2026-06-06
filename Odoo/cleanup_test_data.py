"""Cleanup E2E test data (vendors, RFQs etc. created during testing)"""
import django, os, sys
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
sys.path.insert(0, '.')
django.setup()

from procurement.models import VendorProfile, RFQ, User, ActivityLog, Invoice, PurchaseOrder

# Remove test vendors created by test scripts
test_vendors = ['AutoTest Corp Ltd', 'E2E Test Supplies Ltd']
for name in test_vendors:
    deleted, _ = VendorProfile.objects.filter(name=name).delete()
    if deleted:
        print(f'[OK] Deleted test vendor: {name}')

# Remove test users created by test script
test_users = ['tester.officer@test.com']
for email in test_users:
    deleted, _ = User.objects.filter(email=email).delete()
    if deleted:
        print(f'[OK] Deleted test user: {email}')

# Remove test RFQs
test_rfqs = RFQ.objects.filter(title__icontains='E2E Test')
c = test_rfqs.count()
test_rfqs.delete()
print(f'[OK] Deleted {c} E2E test RFQ(s)')

# Show final counts
print('\nFinal DB state after cleanup:')
from procurement.models import VendorProfile, RFQ, Quotation, Approval, PurchaseOrder, Invoice
print(f'  Vendors:         {VendorProfile.objects.count()}')
print(f'  RFQs:            {RFQ.objects.count()}')
print(f'  Quotations:      {Quotation.objects.count()}')
print(f'  Approvals:       {Approval.objects.count()}')
print(f'  Purchase Orders: {PurchaseOrder.objects.count()}')
print(f'  Invoices:        {Invoice.objects.count()}')
print(f'  Activity Logs:   {ActivityLog.objects.count()}')
print('\nCleanup complete!')
