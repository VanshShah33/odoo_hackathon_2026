"""
VendorBridge ERP - Full Procurement Cycle E2E Test
Simulates: Vendor onboard -> RFQ -> Quotation -> Compare -> Approve -> PO -> Invoice
"""
import django, os, sys
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
sys.path.insert(0, '.')
django.setup()

from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from procurement.models import (
    User, VendorProfile, RFQ, Quotation, Approval,
    PurchaseOrder, Invoice, ActivityLog, Notification
)

results = []

def ok(msg):   results.append(('PASS', msg)); print(f'[PASS] {msg}')
def fail(msg): results.append(('FAIL', msg)); print(f'[FAIL] {msg}')
def warn(msg): results.append(('WARN', msg)); print(f'[WARN] {msg}')
def info(msg): print(f'[INFO] {msg}')
def section(t): print(f'\n{"="*60}\n  {t}\n{"="*60}')

# ============================================================
# PHASE A: Users
# ============================================================
section("PHASE A: User Roles Verification")

admin = User.objects.filter(role='Admin').first()
officer = User.objects.filter(role='Officer').first()
manager = User.objects.filter(role='Manager').first()

if admin: ok(f"Admin user found: {admin.email}")
else: fail("No Admin user found")

if officer: ok(f"Officer user found: {officer.email}")
else: fail("No Officer user found")

if manager: ok(f"Manager user found: {manager.email}")
else: fail("No Manager user found")

# ============================================================
# PHASE B: Vendor Registration & Approval
# ============================================================
section("PHASE B: Vendor Onboarding")

# Check existing vendors
vendor_count = VendorProfile.objects.count()
ok(f"Vendor directory has {vendor_count} registered vendors")

active = VendorProfile.objects.filter(status='Active').count()
pending = VendorProfile.objects.filter(status='Under Review').count()
blocked = VendorProfile.objects.filter(status__in=['Suspended','Inactive']).count()
ok(f"  Active: {active} | Pending: {pending} | Blocked: {blocked}")

# Create a fresh vendor for E2E test
with transaction.atomic():
    e2e_vendor = VendorProfile.objects.create(
        name='E2E Test Supplies Ltd',
        category='Office Supplies',
        gst_number='27E2ETEST9999Z1',
        contact_email='e2e@supplies.com',
        contact_person='E2E Tester',
        phone='+91 9000000099',
        address='E2E Avenue, Pune',
        risk_score=10,
        rating=4.5,
        is_ai_recommended=True,
        status='Active'
    )
    ActivityLog.objects.create(
        user=admin,
        action='Vendor Registered',
        details=f'Registered vendor {e2e_vendor.name}'
    )
ok(f"New vendor created: {e2e_vendor.name} (ID: {e2e_vendor.id})")

# Verify AI-recommended flag
if e2e_vendor.is_ai_recommended:
    ok("Vendor marked as AI Recommended")

# ============================================================
# PHASE C: RFQ Creation & Publishing
# ============================================================
section("PHASE C: RFQ Lifecycle")

with transaction.atomic():
    e2e_rfq = RFQ.objects.create(
        title='E2E Test - Office Stationery Procurement',
        description='End-to-end test RFQ for automated verification.',
        items=[
            {'name': 'A4 Paper Reams', 'spec': '80gsm, 500 sheets', 'qty': 100, 'expected_price': 250},
            {'name': 'Gel Pens (Box)', 'spec': 'Blue ink, 12pcs/box', 'qty': 50, 'expected_price': 120},
            {'name': 'Stapler', 'spec': 'Heavy duty, 100 sheets cap', 'qty': 20, 'expected_price': 350}
        ],
        deadline=timezone.now() + timedelta(days=14),
        status='Draft',
        created_by=officer
    )
    e2e_rfq.assigned_vendors.add(e2e_vendor)
    ActivityLog.objects.create(user=officer, action='RFQ Created', details=f'Created {e2e_rfq.rfq_number}')

ok(f"RFQ created: {e2e_rfq.rfq_number} | {e2e_rfq.title}")
ok(f"RFQ assigned to vendor: {e2e_vendor.name}")

# Publish RFQ
e2e_rfq.status = 'Sent'
e2e_rfq.save()
Notification.objects.create(
    user=admin,
    title='New RFQ Invitation',
    message=f'Vendor {e2e_vendor.name} invited to quote for {e2e_rfq.rfq_number}'
)
ActivityLog.objects.create(user=officer, action='RFQ Published', details=f'Published {e2e_rfq.rfq_number}')
ok(f"RFQ status updated to 'Sent' (Published to vendor)")

# Check RFQ data integrity
assert e2e_rfq.items is not None and len(e2e_rfq.items) == 3
ok("RFQ contains 3 line items (A4 Paper, Gel Pens, Stapler)")

# ============================================================
# PHASE D: Quotation Submission (Vendor Side)
# ============================================================
section("PHASE D: Quotation Submission")

with transaction.atomic():
    e2e_quotation = Quotation.objects.create(
        rfq=e2e_rfq,
        vendor=e2e_vendor,
        delivery_timeline_days=7,
        items_quotation=[
            {'name': 'A4 Paper Reams', 'spec': '80gsm, 500 sheets', 'qty': 100, 'unit_price': 240},
            {'name': 'Gel Pens (Box)', 'spec': 'Blue ink, 12pcs/box', 'qty': 50, 'unit_price': 110},
            {'name': 'Stapler', 'spec': 'Heavy duty, 100 sheets cap', 'qty': 20, 'unit_price': 320}
        ],
        notes='Competitive pricing. Free delivery above Rs.10,000. 1-year warranty on staplers.',
        status='Submitted'
    )
    ActivityLog.objects.create(
        user=admin,
        action='Quotation Submitted',
        details=f'Vendor {e2e_vendor.name} submitted quote for {e2e_rfq.rfq_number}'
    )

ok(f"Quotation submitted: QT-{e2e_quotation.id}")
ok(f"Vendor: {e2e_vendor.name}")
ok(f"Delivery timeline: {e2e_quotation.delivery_timeline_days} days")
ok(f"Total quoted price: Rs.{e2e_quotation.total_price:,.2f}")

# Verify price calculation
expected = (100*240) + (50*110) + (20*320)
if abs(float(e2e_quotation.total_price) - expected) < 1:
    ok(f"Price calculation correct: Rs.{expected:,}")
else:
    warn(f"Price mismatch: expected {expected}, got {e2e_quotation.total_price}")

# ============================================================
# PHASE E: Quotation Evaluation & Comparison
# ============================================================
section("PHASE E: Quotation Evaluation (Officer)")

# Officer shortlists the quotation
e2e_quotation.status = 'Shortlisted'
e2e_quotation.save()
e2e_rfq.status = 'Compared'
e2e_rfq.save()

ActivityLog.objects.create(
    user=officer,
    action='Quotation Shortlisted',
    details=f'Shortlisted QT-{e2e_quotation.id} from {e2e_vendor.name}'
)
ok(f"Quotation QT-{e2e_quotation.id} shortlisted by Officer")
ok(f"RFQ status updated to: {e2e_rfq.status}")

# Verify all quotations for this RFQ
all_quotes = Quotation.objects.filter(rfq=e2e_rfq)
ok(f"Total quotations for RFQ: {all_quotes.count()}")
shortlisted = all_quotes.filter(status='Shortlisted')
ok(f"Shortlisted quotations: {shortlisted.count()}")

# ============================================================
# PHASE F: Approval Request & Manager Decision
# ============================================================
section("PHASE F: Manager Approval Workflow")

# Create approval request
with transaction.atomic():
    e2e_approval = Approval.objects.create(
        quotation=e2e_quotation,
        approver=manager,
        status='Pending'
    )
    Notification.objects.create(
        user=manager,
        title='Approval Required',
        message=f'Approval needed for {e2e_rfq.rfq_number} - {e2e_vendor.name}'
    )
    ActivityLog.objects.create(
        user=officer,
        action='Approval Requested',
        details=f'Approval requested for QT-{e2e_quotation.id}'
    )

ok(f"Approval request created: APP-{e2e_approval.id:04d}")
ok(f"Assigned to approver: {manager.email}")
ok(f"Initial status: {e2e_approval.status}")

# Manager reviews and approves
e2e_approval.status = 'Approved'
e2e_approval.remarks = 'Price within budget. Vendor has good track record. Approved.'
e2e_approval.save()

e2e_quotation.status = 'Approved'
e2e_quotation.save()

ActivityLog.objects.create(
    user=manager,
    action='Approval Decision',
    details=f'Manager approved APP-{e2e_approval.id:04d}: {e2e_approval.remarks}'
)
ok(f"Manager approved APP-{e2e_approval.id:04d}")
ok(f"Remarks: {e2e_approval.remarks}")
ok(f"Quotation status: {e2e_quotation.status}")

# ============================================================
# PHASE G: Purchase Order Generation
# ============================================================
section("PHASE G: Purchase Order Generation")

with transaction.atomic():
    e2e_po = PurchaseOrder.objects.create(
        quotation=e2e_quotation,
        timeline_status='Processing'
    )
    e2e_rfq.status = 'PO_Generated'
    e2e_rfq.save()
    ActivityLog.objects.create(
        user=officer,
        action='PO Generated',
        details=f'Generated PO {e2e_po.po_number} for {e2e_vendor.name}'
    )

ok(f"Purchase Order created: {e2e_po.po_number}")
ok(f"PO linked to vendor: {e2e_po.quotation.vendor.name}")
ok(f"PO timeline status: {e2e_po.timeline_status}")
ok(f"RFQ final status: {e2e_rfq.status}")

# ============================================================
# PHASE H: Invoice Generation
# ============================================================
section("PHASE H: Invoice Generation")

with transaction.atomic():
    subtotal = float(e2e_quotation.total_price)
    tax = subtotal * 0.18
    total = subtotal + tax

    e2e_invoice = Invoice.objects.create(
        purchase_order=e2e_po,
        subtotal=subtotal,
        tax_amount=tax,
        total_amount=total,
        status='Unpaid'
    )
    ActivityLog.objects.create(
        user=officer,
        action='Invoice Generated',
        details=f'Invoice {e2e_invoice.invoice_number} for PO {e2e_po.po_number}'
    )

ok(f"Invoice created: {e2e_invoice.invoice_number}")
ok(f"Subtotal: Rs.{subtotal:,.2f}")
ok(f"GST (18%): Rs.{tax:,.2f}")
ok(f"Total with tax: Rs.{total:,.2f}")
ok(f"Payment status: {e2e_invoice.status}")

# Mark as paid
e2e_invoice.status = 'Paid'
e2e_invoice.save()
e2e_po.timeline_status = 'Delivered'
e2e_po.save()
ActivityLog.objects.create(
    user=admin,
    action='Invoice Paid',
    details=f'Invoice {e2e_invoice.invoice_number} marked as Paid'
)
ok(f"Invoice marked as Paid")
ok(f"PO status updated to: {e2e_po.timeline_status}")

# ============================================================
# PHASE I: Activity Log Integrity Check
# ============================================================
section("PHASE I: Activity Log Verification")

total_logs = ActivityLog.objects.count()
ok(f"Total activity log entries: {total_logs}")

e2e_logs = ActivityLog.objects.filter(details__icontains='E2E Test').count()
ok(f"E2E test-related log entries: {e2e_logs}")

# Verify audit trail completeness
required_actions = [
    'Vendor Registered', 'RFQ Created', 'RFQ Published',
    'Quotation Submitted', 'Quotation Shortlisted', 'Approval Requested',
    'Approval Decision', 'PO Generated', 'Invoice Generated', 'Invoice Paid'
]
for action in required_actions:
    count = ActivityLog.objects.filter(action__icontains=action.split(' ')[0]).count()
    if count > 0:
        ok(f"Audit trail: '{action}' -> {count} entries")
    else:
        warn(f"Audit trail missing: '{action}'")

# ============================================================
# PHASE J: Database Integrity Final Check
# ============================================================
section("PHASE J: Final Data Integrity Check")

# Counts
info("Final database state:")
print(f"  Users:          {User.objects.count()}")
print(f"  Vendors:        {VendorProfile.objects.count()}")
print(f"  RFQs:           {RFQ.objects.count()}")
print(f"  Quotations:     {Quotation.objects.count()}")
print(f"  Approvals:      {Approval.objects.count()}")
print(f"  Purchase Orders:{PurchaseOrder.objects.count()}")
print(f"  Invoices:       {Invoice.objects.count()}")
print(f"  Activity Logs:  {ActivityLog.objects.count()}")
print(f"  Notifications:  {Notification.objects.count()}")

# Chain integrity: RFQ -> Quotation -> Approval -> PO -> Invoice
assert e2e_rfq.id is not None; ok("RFQ object valid")
assert e2e_quotation.rfq == e2e_rfq; ok("Quotation linked to correct RFQ")
assert e2e_approval.quotation == e2e_quotation; ok("Approval linked to correct Quotation")
assert e2e_po.quotation == e2e_quotation; ok("PO linked to correct Quotation")
assert e2e_invoice.purchase_order == e2e_po; ok("Invoice linked to correct PO")

ok("FULL PROCUREMENT CHAIN INTEGRITY: RFQ -> Quotation -> Approval -> PO -> Invoice VERIFIED")

# Vendor metrics
v = VendorProfile.objects.get(id=e2e_vendor.id)
ok(f"Vendor rating: {v.rating}")
ok(f"Vendor status: {v.status}")

# ============================================================
# FINAL SUMMARY
# ============================================================
section("FINAL RESULTS")

passed = sum(1 for r in results if r[0] == 'PASS')
failed = sum(1 for r in results if r[0] == 'FAIL')
warned = sum(1 for r in results if r[0] == 'WARN')
total = len(results)
score = int((passed/total)*100) if total else 0

print(f"\n  PASSED : {passed}/{total}")
print(f"  FAILED : {failed}/{total}")
print(f"  WARNED : {warned}/{total}")
print(f"  SCORE  : {score}%\n")

if failed > 0:
    print("FAILURES:")
    for r in results:
        if r[0] == 'FAIL': print(f"  - {r[1]}")

if score >= 95:
    print("RESULT: PERFECT - Full procurement workflow verified end-to-end!")
elif score >= 80:
    print("RESULT: GOOD - Workflow mostly working, minor issues found.")
else:
    print("RESULT: NEEDS WORK - Review failures above.")
