"""Test all 4 role dashboards render correctly"""
import requests, sys
sys.stdout.reconfigure(encoding='utf-8')

BASE = 'http://127.0.0.1:8000'
roles = [
    ('admin@vendorbridge.com',   'test123', 'Admin'),
    ('officer@vendorbridge.com', 'test123', 'Officer'),
    ('manager@vendorbridge.com', 'test123', 'Manager'),
    ('tirth12@gmail.com',        'tirth123', 'Vendor'),
]

for email, pw, role in roles:
    s = requests.Session()
    r = s.get(f'{BASE}/login/')
    csrf = s.cookies.get('csrftoken')
    r = s.post(f'{BASE}/login/', data={'email':email,'password':pw,'csrfmiddlewaretoken':csrf}, allow_redirects=True)
    if '/login/' not in r.url and r.status_code == 200:
        dash = s.get(f'{BASE}/')
        kpi_checks = {
            'Admin':   ['Total Users','Total Vendors','System Administration'],
            'Officer': ['Total RFQs','Procurement Command Center'],
            'Manager': ['Approval Command Center','Pending Approvals'],
            'Vendor':  ['Supplier Portal','RFQs Received'],
        }
        checks = kpi_checks.get(role, [])
        passed = all(k in dash.text for k in checks)
        status = '[PASS]' if passed else '[FAIL]'
        missing = [k for k in checks if k not in dash.text]
        print(f'{status} {role} dashboard (HTTP {dash.status_code})', end='')
        if missing: print(f' -- Missing: {missing}', end='')
        print()
    else:
        print(f'[FAIL] {role} login failed (redirect to {r.url})')
    try:
        s.post(f'{BASE}/logout/', data={'csrfmiddlewaretoken': s.cookies.get('csrftoken')})
    except Exception:
        pass
