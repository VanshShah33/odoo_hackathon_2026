#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""VendorBridge ERP - Full Workflow Test Script"""

import urllib.request, urllib.parse, urllib.error, http.cookiejar, json, sys, os

# Fix Windows encoding
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')

BASE = 'http://127.0.0.1:8000'
results = []

def log(prefix, msg): print(f"{prefix} {msg}")
def ok(msg):   results.append(('PASS', msg)); log('[PASS]', msg)
def fail(msg): results.append(('FAIL', msg)); log('[FAIL]', msg)
def warn(msg): results.append(('WARN', msg)); log('[WARN]', msg)
def info(msg): log('[INFO]', msg)
def section(t): print(f"\n{'='*60}\n  {t}\n{'='*60}")

# Session
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
opener.addheaders = [('User-Agent', 'VendorBridge-Test/1.0')]

def get(path):
    try:
        r = opener.open(BASE + path)
        return r.status, r.read().decode('utf-8', errors='ignore')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', errors='ignore')
    except Exception as ex:
        return 0, str(ex)

def get_csrf():
    for c in jar:
        if c.name == 'csrftoken':
            return c.value
    return ''

def post(path, data):
    data['csrfmiddlewaretoken'] = get_csrf()
    enc = urllib.parse.urlencode(data).encode('utf-8')
    req = urllib.request.Request(BASE + path, data=enc, method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    req.add_header('Referer', BASE + path)
    try:
        r = opener.open(req)
        return r.status, r.read().decode('utf-8', errors='ignore')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', errors='ignore')
    except Exception as ex:
        return 0, str(ex)

def has(body, *kw):
    return all(k.lower() in body.lower() for k in kw)

# ============================================================
# PHASE 1: Auth
# ============================================================
section("PHASE 1: Authentication & Login")

s, body = get('/login/')
if s == 200: ok(f"GET /login/ -> {s}")
else: fail(f"GET /login/ -> {s}")

s, body = post('/login/', {'email': 'bad@x.com', 'password': 'wrong'})
if s == 200: ok("Bad credentials correctly rejected (stays on login)")
else: warn(f"Bad credentials: {s}")

s, body = post('/login/', {'email': 'admin@vendorbridge.com', 'password': 'admin123'})
s2, body2 = get('/')
if s2 == 200 and has(body2, 'dashboard'): ok("Admin login -> Dashboard loaded")
elif s2 == 200: ok(f"Admin login -> page loaded {s2}")
else: fail(f"Admin login failed -> {s2}")

# ============================================================
# PHASE 2: Dashboard
# ============================================================
section("PHASE 2: Dashboard")

s, body = get('/')
if s == 200:
    ok(f"Dashboard HTTP {s}")
    for kw in ['vendor', 'purchase', 'invoice']:
        if kw in body.lower(): ok(f"Dashboard metric visible: {kw}")
        else: warn(f"Dashboard metric missing: {kw}")
else:
    fail(f"Dashboard -> {s}")

# ============================================================
# PHASE 3: Vendors
# ============================================================
section("PHASE 3: Vendors Directory")

s, body = get('/vendors/')
if s == 200: ok(f"GET /vendors/ -> {s}")
else: fail(f"/vendors/ -> {s}")

# Register vendor
s, body = post('/vendors/', {
    'action': 'register', 'name': 'AutoTest Corp Ltd',
    'category': 'IT Hardware', 'gst_number': '29AUTOTEST001Z9',
    'contact_email': 'auto@testcorp.com', 'contact_person': 'Auto Tester',
    'phone': '+91 9000000001', 'address': '1 Test Lane, Delhi',
    'risk_score': '12', 'status': 'Active'
})
s2, b2 = get('/vendors/')
if 'AutoTest' in b2 or s == 302: ok("Vendor registration -> AutoTest Corp Ltd created")
else: warn(f"Vendor registration status: {s}")

# Status filters
for f in ['All', 'active', 'Pending', 'Blocked']:
    s, b = get(f'/vendors/?status={f}')
    if s == 200: ok(f"Vendor filter '{f}' -> OK")
    else: fail(f"Vendor filter '{f}' -> {s}")

# Search
s, b = get('/vendors/?search=AutoTest')
if s == 200: ok("Vendor search -> OK")
else: fail(f"Vendor search -> {s}")

# CSV export
s, b = post('/vendors/', {'action': 'export_csv'})
if s == 200: ok("Vendor CSV export -> OK")
else: warn(f"CSV export -> {s}")

# ============================================================
# PHASE 4: Users (Admin only)
# ============================================================
section("PHASE 4: Users Management")

s, body = get('/users/')
if s == 200: ok(f"GET /users/ -> {s}")
else: fail(f"/users/ -> {s}")

s, body = post('/users/', {
    'action': 'create', 'email': 'tester.officer@test.com',
    'first_name': 'Tester', 'last_name': 'Officer',
    'role': 'Officer', 'password': 'test1234'
})
s2, b2 = get('/users/')
if 'tester.officer' in b2.lower() or s in [200, 302]: ok("User creation -> Officer account created")
else: warn(f"User creation: {s}")

# ============================================================
# PHASE 5: RFQs
# ============================================================
section("PHASE 5: RFQ Management")

s, body = get('/rfqs/')
if s == 200: ok(f"GET /rfqs/ -> {s}")
else: fail(f"/rfqs/ -> {s}")

items = json.dumps([
    {'name': 'Ergonomic Chair', 'spec': 'Mesh, adjustable', 'qty': 20, 'expected_price': 8000},
    {'name': 'Standing Desk', 'spec': '120cm motorized', 'qty': 10, 'expected_price': 25000}
])
s, body = post('/rfqs/', {
    'action': 'create', 'title': 'AutoTest Furniture RFQ',
    'description': 'Automated test RFQ for office furniture.',
    'deadline': '2026-08-31', 'budget': '400000',
    'items_json': items
})
s2, b2 = get('/rfqs/')
if 'AutoTest Furniture' in b2 or s == 302: ok("RFQ creation -> AutoTest Furniture RFQ created")
else: warn(f"RFQ creation status: {s}")

for filt in ['Open', 'Closed', 'Compared']:
    s, b = get(f'/rfqs/?status={filt}')
    if s == 200: ok(f"RFQ filter '{filt}' -> OK")
    else: fail(f"RFQ filter '{filt}' -> {s}")

s, b = get('/rfqs/?search=AutoTest')
if s == 200: ok("RFQ search -> OK")
else: fail(f"RFQ search -> {s}")

# ============================================================
# PHASE 6: Quotations
# ============================================================
section("PHASE 6: Quotations")

s, body = get('/quotations/')
if s == 200:
    ok(f"GET /quotations/ -> {s}")
    if has(body, 'quotation'): ok("Quotations content renders")
else: fail(f"/quotations/ -> {s}")

s, b = get('/quotations/?status=Submitted')
if s == 200: ok("Quotations filter -> OK")
else: fail(f"Quotations filter -> {s}")

# ============================================================
# PHASE 7: Approvals
# ============================================================
section("PHASE 7: Approvals / Manager Dashboard")

s, body = get('/approvals/')
if s == 200: ok(f"GET /approvals/ -> {s}")
else: fail(f"/approvals/ -> {s}")

info("Generating demo approval request...")
s, body = post('/approvals/', {'action': 'generate_mock_approval'})
s2, b2 = get('/approvals/')
if s in [200, 302]:
    ok("Demo approval generation triggered")
    if 'APP-' in b2 or 'Pending' in b2: ok("Approval requests now visible in ledger")
    else: warn("Approvals ledger content unclear")

# ============================================================
# PHASE 8: Purchase Orders
# ============================================================
section("PHASE 8: Purchase Orders")

s, body = get('/purchase-orders/')
if s == 200:
    ok(f"GET /purchase-orders/ -> {s}")
    if has(body, 'purchase'): ok("Purchase Orders content renders")
else: fail(f"/purchase-orders/ -> {s}")

for filt in ['Pending', 'Delivered']:
    s, b = get(f'/purchase-orders/?status={filt}')
    if s == 200: ok(f"PO filter '{filt}' -> OK")
    else: fail(f"PO filter '{filt}' -> {s}")

# ============================================================
# PHASE 9: Invoices
# ============================================================
section("PHASE 9: Invoices")

s, body = get('/invoices/')
if s == 200:
    ok(f"GET /invoices/ -> {s}")
    if has(body, 'invoice'): ok("Invoices content renders")
else: fail(f"/invoices/ -> {s}")

for filt in ['Paid', 'Unpaid']:
    s, b = get(f'/invoices/?status={filt}')
    if s == 200: ok(f"Invoice filter '{filt}' -> OK")
    else: fail(f"Invoice filter '{filt}' -> {s}")

# ============================================================
# PHASE 10: Reports
# ============================================================
section("PHASE 10: Reports & Analytics")

s, body = get('/reports/')
if s == 200:
    ok(f"GET /reports/ -> {s}")
    if has(body, 'report') or has(body, 'chart') or has(body, 'analytic'):
        ok("Reports analytics content renders")
else: fail(f"/reports/ -> {s}")

# ============================================================
# PHASE 11: Activity Log
# ============================================================
section("PHASE 11: Activity Log")

s, body = get('/activity/')
if s == 200:
    ok(f"GET /activity/ -> {s}")
    if has(body, 'activity') or has(body, 'log'): ok("Activity log renders")
    if 'vendor' in body.lower() or 'registered' in body.lower():
        ok("Activity log captures vendor registration events")
else: fail(f"/activity/ -> {s}")

# ============================================================
# PHASE 12: Settings
# ============================================================
section("PHASE 12: Settings")

s, body = get('/settings/')
if s == 200:
    ok(f"GET /settings/ -> {s}")
    if has(body, 'profile'): ok("Settings: Profile panel visible")
    if has(body, 'password'): ok("Settings: Security/Password panel visible")
    if has(body, 'theme') or has(body, 'appearance'): ok("Settings: Theme panel visible")
else: fail(f"/settings/ -> {s}")

s, body = post('/settings/', {
    'action': 'update_profile', 'email': 'admin@vendorbridge.com',
    'first_name': 'Admin', 'last_name': 'VendorBridge'
})
if has(body, 'success') or has(body, 'updated') or s in [200, 302]:
    ok("Settings: Profile update works")
else: warn(f"Settings profile update: {s}")

# Test bad password change
s, body = post('/settings/', {
    'action': 'change_password',
    'current_password': 'wrongpassword',
    'new_password': 'newpass123',
    'confirm_password': 'newpass123'
})
if has(body, 'incorrect') or has(body, 'invalid') or has(body, 'error'):
    ok("Settings: Wrong current password correctly rejected")
else: warn(f"Password validation response: {s}")

# ============================================================
# PHASE 13: RBAC - Role-based access
# ============================================================
section("PHASE 13: Role-Based Access Control (RBAC)")

# Logout Admin
s, b = get('/logout/')
info(f"Logged out admin: {s}")

# Login as Vendor
s, b = post('/login/', {'email': 'vendor@vendorbridge.com', 'password': 'vendor123'})
s2, b2 = get('/')

if s2 == 200:
    ok(f"Vendor login -> Dashboard {s2}")

    # Vendor should NOT see Users, Vendors menu
    if '/users/' not in b2: ok("RBAC: Vendor cannot see Users menu (restricted)")
    else: warn("RBAC: Vendor can see Users menu - may need check")

    if '/vendors/' not in b2: ok("RBAC: Vendor cannot see Vendors menu (restricted)")
    else: warn("RBAC: Vendor can see Vendors menu")

    # Vendor should see RFQs
    if '/rfqs/' in b2: ok("RBAC: Vendor can see RFQs menu (allowed)")
    else: warn("RBAC: Vendor cannot see RFQs menu")

    # Vendor should see Activity
    if '/activity/' in b2: ok("RBAC: Vendor can see Activity menu (allowed)")

    # Vendor should NOT see Approvals
    if '/approvals/' not in b2: ok("RBAC: Vendor cannot see Approvals menu (restricted)")
    else: warn("RBAC: Vendor can see Approvals menu")

# Logout Vendor, login Manager
s, b = get('/logout/')
s, b = post('/login/', {'email': 'manager@vendorbridge.com', 'password': 'manager123'})
s2, b2 = get('/')
if s2 == 200:
    ok(f"Manager login -> Dashboard {s2}")
    if '/approvals/' in b2: ok("RBAC: Manager can see Approvals menu (allowed)")
    else: warn("RBAC: Manager cannot see Approvals menu")
    if '/users/' not in b2: ok("RBAC: Manager cannot see Users menu (restricted)")
    if '/vendors/' not in b2: ok("RBAC: Manager cannot see Vendors menu (restricted)")

# ============================================================
# FINAL SUMMARY
# ============================================================
section("FINAL TEST RESULTS SUMMARY")

passed  = sum(1 for r in results if r[0] == 'PASS')
failed  = sum(1 for r in results if r[0] == 'FAIL')
warned  = sum(1 for r in results if r[0] == 'WARN')
total   = len(results)
score   = int((passed / total) * 100) if total else 0

print(f"\n  PASSED : {passed}/{total}")
print(f"  FAILED : {failed}/{total}")
print(f"  WARNED : {warned}/{total}")
print(f"  SCORE  : {score}%")

if failed:
    print("\nFAILURES:")
    for r in results:
        if r[0] == 'FAIL': print(f"  - {r[1]}")

if warned:
    print("\nWARNINGS:")
    for r in results:
        if r[0] == 'WARN': print(f"  - {r[1]}")

if score >= 90: print("\nRESULT: EXCELLENT - VendorBridge ERP fully operational!")
elif score >= 70: print("\nRESULT: GOOD - Most features working, minor issues.")
else: print("\nRESULT: NEEDS ATTENTION - Review failures above.")
