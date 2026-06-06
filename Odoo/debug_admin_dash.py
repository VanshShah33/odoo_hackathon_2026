"""Debug Admin dashboard 500"""
import django, os, sys
sys.stdout.reconfigure(encoding='utf-8')
os.environ['DJANGO_SETTINGS_MODULE'] = 'backend.settings'
sys.path.insert(0, '.')
django.setup()

from django.test import RequestFactory, Client
from procurement.models import User

c = Client()
admin = User.objects.get(email='admin@vendorbridge.com')
c.force_login(admin)
resp = c.get('/')
print(f'Status: {resp.status_code}')
if resp.status_code == 500:
    # Try to capture the exception
    try:
        from procurement.views import dashboard_view
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        request.user = admin
        # Add session
        from django.contrib.sessions.backends.db import SessionStore
        request.session = SessionStore()
        
        result = dashboard_view(request)
        print('View ran OK')
    except Exception as e:
        import traceback
        print(f'Exception: {e}')
        traceback.print_exc()
