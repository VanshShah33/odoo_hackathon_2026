from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'users', views.UserViewSet, basename='user')
router.register(r'vendors', views.VendorProfileViewSet, basename='vendor')
router.register(r'rfqs', views.RFQViewSet, basename='rfq')
router.register(r'quotations', views.QuotationViewSet, basename='quotation')
router.register(r'approvals', views.ApprovalViewSet, basename='approval')
router.register(r'pos', views.PurchaseOrderViewSet, basename='po')
router.register(r'invoices', views.InvoiceViewSet, basename='invoice')
router.register(r'activities', views.ActivityLogViewSet, basename='activity')
router.register(r'notifications', views.NotificationViewSet, basename='notification')

urlpatterns = [
    # SSR HTML Template views
    path('', views.dashboard_view, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('switch-role/', views.switch_role_view, name='switch_role'),
    path('vendors/', views.vendors_view, name='vendors'),
    path('rfqs/', views.rfqs_view, name='rfqs'),
    path('rfqs/<int:pk>/compare/', views.rfq_compare_view, name='rfq_compare'),
    path('quotations/', views.quotations_view, name='quotations'),
    path('approvals/', views.approvals_view, name='approvals'),
    path('purchase-orders/', views.purchase_orders_view, name='purchase_orders'),
    path('invoices/', views.invoices_view, name='invoices'),
    path('reports/', views.reports_view, name='reports'),
    path('activity/', views.activity_view, name='activity'),
    path('users/', views.users_view, name='users'),
    path('settings/', views.settings_view, name='settings'),

    # REST framework API endpoints
    path('api/', include(router.urls)),
]
