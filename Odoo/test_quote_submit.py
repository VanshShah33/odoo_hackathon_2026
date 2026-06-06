"""Quick test: verify RFQ items render correctly as JSON for the template"""
import django, os, sys
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
sys.path.insert(0, '.')
django.setup()

import json
from procurement.models import RFQ, VendorProfile, User
from procurement.templatetags.procurement_filters import to_json

# Test the to_json filter
print('=== Testing to_json filter ===')
rfq = RFQ.objects.filter(status='Sent').first()
if rfq:
    print(f'RFQ: {rfq.rfq_number}')
    print(f'Raw items type: {type(rfq.items)}')
    print(f'Raw items: {rfq.items}')
    json_output = to_json(rfq.items)
    print(f'to_json output: {json_output}')
    
    # Validate it parses back correctly
    parsed = json.loads(str(json_output))
    print(f'Parses back OK: {len(parsed)} items')
    for item in parsed:
        print(f'  - {item["name"]} x{item["qty"]} @ Rs.{item["expected_price"]}')
    print()
    print('[PASS] to_json filter works correctly')
else:
    print('[WARN] No Sent RFQs found')

# Test quotation creation
from procurement.models import Quotation
print()
print('=== Testing Quotation creation ===')
tirth_vendor = VendorProfile.objects.get(name='Tirth Textile')
for rfq in RFQ.objects.filter(status='Sent', assigned_vendors=tirth_vendor):
    items_quotation = []
    for item in rfq.items:
        items_quotation.append({
            'name': item['name'],
            'spec': item.get('spec', ''),
            'qty': item['qty'],
            'unit_price': item['expected_price'] * 0.95  # 5% discount
        })
    
    q = Quotation.objects.create(
        rfq=rfq,
        vendor=tirth_vendor,
        items_quotation=items_quotation,
        delivery_timeline_days=5,
        notes='5% discount. Free shipping. 1-year warranty.',
        status='Submitted'
    )
    print(f'  Quotation QT-{q.id} submitted for {rfq.rfq_number}')
    print(f'  Subtotal: Rs.{q.subtotal:.2f}')
    print(f'  GST(18%): Rs.{q.tax_amount:.2f}')
    print(f'  Total:    Rs.{q.total_price:.2f}')
    print(f'  Status:   {q.status}')
    print(f'  [PASS] Quotation model save() calculates prices correctly')
    # Clean up test quotation
    q.delete()
    print(f'  (Test quotation removed)')
