import django, os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
sys.path.insert(0, '.')
django.setup()

from procurement.models import User, VendorProfile, RFQ, Quotation, Approval, ActivityLog, PurchaseOrder, Invoice

print('=== USERS IN DATABASE ===')
for u in User.objects.all():
    print(f'  Email: {u.email} | Role: {u.role} | Active: {u.is_active}')

print()
print('=== VENDOR PROFILES ===')
for v in VendorProfile.objects.all()[:20]:
    print(f'  {v.name} | {v.category} | Status: {v.status} | Rating: {v.rating}')

print()
print('=== RFQs ===')
for r in RFQ.objects.all()[:20]:
    vendors = list(r.assigned_vendors.values_list('name', flat=True))
    print(f'  {r.rfq_number} | {r.title[:35]} | Status: {r.status} | Vendors: {vendors}')

print()
print('=== QUOTATIONS ===')
for q in Quotation.objects.all()[:15]:
    print(f'  QT-{q.id} | Vendor: {q.vendor.name} | Status: {q.status} | Total: {q.total_price}')

print()
print('=== APPROVALS ===')
for a in Approval.objects.all()[:10]:
    print(f'  APP-{a.id:04d} | {a.quotation.rfq.rfq_number} | Status: {a.status} | Approver: {a.approver.email}')

print()
print('=== PURCHASE ORDERS ===')
for po in PurchaseOrder.objects.all()[:10]:
    print(f'  {po.po_number} | Status: {po.timeline_status} | Vendor: {po.quotation.vendor.name}')

print()
print('=== INVOICES ===')
for inv in Invoice.objects.all()[:10]:
    print(f'  {inv.invoice_number} | PO: {inv.purchase_order.po_number} | Status: {inv.status} | Total: {inv.total_amount}')

print()
print('=== RECENT ACTIVITY LOG ===')
for l in ActivityLog.objects.order_by('-timestamp')[:15]:
    ts = l.timestamp.strftime('%Y-%m-%d %H:%M')
    print(f'  {ts} | {l.action} | {l.details[:55]}')
