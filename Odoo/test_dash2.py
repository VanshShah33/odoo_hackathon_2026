import django, os, sys
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
sys.path.insert(0, '.')
django.setup()
from django.test import Client
from procurement.models import User

c = Client()
checks = {
    'Admin':   ['Total Users', 'Total Vendors', 'System Administration'],
    'Officer': ['Total RFQs', 'Procurement Command Center', 'Open RFQs'],
    'Manager': ['Approval Command Center', 'Pending Approvals'],
    'Vendor':  ['Supplier Portal', 'RFQs Received'],
}
for email in ['admin@vendorbridge.com','officer@vendorbridge.com','manager@vendorbridge.com','tirth12@gmail.com']:
    u = User.objects.get(email=email)
    c.force_login(u)
    resp = c.get('/')
    text = resp.content.decode('utf-8', errors='replace')
    role = u.role
    kpi = checks.get(role, [])
    ok = all(k in text for k in kpi)
    missing = [k for k in kpi if k not in text]
    tag = 'PASS' if ok else 'FAIL'
    line = f'[{tag}] {role} ({email}) HTTP {resp.status_code}'
    if missing:
        line += f' -- missing: {missing}'
    print(line)
