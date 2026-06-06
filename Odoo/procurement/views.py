from django.shortcuts import get_object_or_404
from django.core.mail import send_mail
from django.db import transaction
from django.contrib.auth import authenticate
from django.http import HttpResponse
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.barcode.qr import QrCodeWidget

from .models import User, VendorProfile, RFQ, Quotation, Approval, PurchaseOrder, Invoice, ActivityLog, Notification
from .serializers import (
    UserSerializer, VendorProfileSerializer, RFQSerializer, QuotationSerializer,
    ApprovalSerializer, PurchaseOrderSerializer, InvoiceSerializer, ActivityLogSerializer, NotificationSerializer
)
from .simulation import trigger_simulation

def resolve_user_from_request(request):
    """
    Helper to resolve user from custom header 'X-User-Email'.
    This is bypass-safe for local offline presentation without cookie/session complications.
    """
    email = request.headers.get('X-User-Email')
    if email:
        user = User.objects.filter(email=email).first()
        if user:
            return user
    if request.user and request.user.is_authenticated:
        return request.user
    # Fallback to first officer or admin if none is authenticated for fallback safety
    return User.objects.first()

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [AllowAny]

    @action(detail=False, methods=['post'])
    def register(self, request):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            with transaction.atomic():
                user = serializer.save()
                # If role is Vendor, create Vendor Profile automatically
                if user.role == 'Vendor':
                    vendor_name = request.data.get('vendor_name', f"{user.first_name} {user.last_name} Corp")
                    category = request.data.get('category', 'General')
                    gst_number = request.data.get('gst_number', f"27AAAAA{user.id:04d}A1Z1")
                    phone = request.data.get('phone', '0000000000')
                    address = request.data.get('address', 'Enter Address')
                    
                    VendorProfile.objects.create(
                        user=user,
                        name=vendor_name,
                        category=category,
                        gst_number=gst_number,
                        contact_email=user.email,
                        phone=phone,
                        address=address,
                        status='Active'
                    )
                
                # Create activity log
                ActivityLog.objects.create(
                    user=user,
                    action="User Registered",
                    details=f"User {user.email} registered as {user.role}."
                )
                
                return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'])
    def login(self, request):
        email = request.data.get('email')
        password = request.data.get('password')
        
        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
            
        user = User.objects.filter(email=email).first()
        if user:
            # For hackathon demo ease, check password if set, else allow direct login for seeded users
            if password:
                authenticated_user = authenticate(username=email, password=password)
                if not authenticated_user:
                    return Response({'error': 'Invalid credentials'}, status=status.HTTP_400_BAD_REQUEST)
                user = authenticated_user

            # Retrieve vendor profile id if user is a vendor
            vendor_profile_id = None
            if user.role == 'Vendor' and hasattr(user, 'vendor_profile'):
                vendor_profile_id = user.vendor_profile.id

            data = UserSerializer(user).data
            data['vendor_profile_id'] = vendor_profile_id
            
            ActivityLog.objects.create(
                user=user,
                action="User Logged In",
                details=f"User {user.email} logged in successfully."
            )
            return Response(data, status=status.HTTP_200_OK)
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'])
    def me(self, request):
        user = resolve_user_from_request(request)
        if user:
            vendor_profile_id = None
            if user.role == 'Vendor' and hasattr(user, 'vendor_profile'):
                vendor_profile_id = user.vendor_profile.id
            data = UserSerializer(user).data
            data['vendor_profile_id'] = vendor_profile_id
            return Response(data)
        return Response({'error': 'Not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)


class VendorProfileViewSet(viewsets.ModelViewSet):
    queryset = VendorProfile.objects.all()
    serializer_class = VendorProfileSerializer
    permission_classes = [AllowAny]


class RFQViewSet(viewsets.ModelViewSet):
    queryset = RFQ.objects.all().order_by('-created_at')
    serializer_class = RFQSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        user = resolve_user_from_request(self.request)
        rfq = serializer.save(created_by=user or User.objects.first())
        
        # Log activity
        ActivityLog.objects.create(
            user=user,
            action="RFQ Created",
            details=f"Created RFQ {rfq.rfq_number}: {rfq.title}"
        )

    @action(detail=True, methods=['post'])
    def send_rfq(self, request, pk=None):
        rfq = self.get_object()
        user = resolve_user_from_request(request)
        
        if rfq.status != 'Draft':
            return Response({'error': 'Can only send RFQ from Draft status'}, status=status.HTTP_400_BAD_REQUEST)
            
        rfq.status = 'Sent'
        rfq.save()
        
        # Log activity
        ActivityLog.objects.create(
            user=user,
            action="RFQ Published/Sent",
            details=f"Published RFQ {rfq.rfq_number} and notified assigned vendors."
        )
        
        # Notify vendors
        for vendor in rfq.assigned_vendors.all():
            if vendor.user:
                Notification.objects.create(
                    user=vendor.user,
                    title="New RFQ Invitation",
                    message=f"You have been invited to quote for {rfq.rfq_number} ({rfq.title}). Deadline: {rfq.deadline.strftime('%Y-%m-%d')}."
                )

        # Trigger live vendor quotation bidding simulation!
        trigger_simulation(rfq.id)
        
        return Response(RFQSerializer(rfq).data, status=status.HTTP_200_OK)


class QuotationViewSet(viewsets.ModelViewSet):
    queryset = Quotation.objects.all().order_by('-created_at')
    serializer_class = QuotationSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        user = resolve_user_from_request(self.request)
        quote = serializer.save()
        
        # Log activity
        ActivityLog.objects.create(
            user=user,
            action="Quotation Draft Created",
            details=f"Drafted quotation for {quote.rfq.rfq_number}."
        )

    @action(detail=True, methods=['post'])
    def submit_quotation(self, request, pk=None):
        quote = self.get_object()
        user = resolve_user_from_request(request)
        
        quote.status = 'Submitted'
        quote.save()

        # Check if all quotes for RFQ are submitted to auto transition RFQ state
        rfq = quote.rfq
        if rfq.status == 'Sent':
            rfq.status = 'Received'
            rfq.save()

        # Log activity
        ActivityLog.objects.create(
            user=user,
            action="Quotation Submitted",
            details=f"Vendor '{quote.vendor.name}' submitted quotation for {rfq.rfq_number}. Total: ₹{quote.total_price:.2f}"
        )
        
        # Notify Procurement Officer
        Notification.objects.create(
            user=rfq.created_by,
            title="Quotation Submitted",
            message=f"Vendor '{quote.vendor.name}' has submitted a quotation for {rfq.rfq_number}."
        )

        return Response(QuotationSerializer(quote).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def submit_for_approval(self, request, pk=None):
        quote = self.get_object()
        user = resolve_user_from_request(request)
        
        with transaction.atomic():
            quote.status = 'Shortlisted'
            quote.save()
            
            rfq = quote.rfq
            rfq.status = 'Compared'
            rfq.save()
            
            # Find managers to notify
            managers = User.objects.filter(role='Manager')
            if not managers.exists():
                # fallback notifications to all users if no manager exists
                managers = User.objects.all()

            for manager in managers:
                # Create Approval request
                Approval.objects.create(
                    quotation=quote,
                    approver=manager,
                    status='Pending'
                )
                # Notify manager
                Notification.objects.create(
                    user=manager,
                    title="Procurement Approval Request",
                    message=f"Approval requested for quotation from '{quote.vendor.name}' on {rfq.rfq_number} ({rfq.title})."
                )

            # Log activity
            ActivityLog.objects.create(
                user=user,
                action="Quotation Submitted for Approval",
                details=f"Quotation from '{quote.vendor.name}' for {rfq.rfq_number} sent for approval."
            )

        return Response(QuotationSerializer(quote).data, status=status.HTTP_200_OK)


class ApprovalViewSet(viewsets.ModelViewSet):
    queryset = Approval.objects.all().order_by('-created_at')
    serializer_class = ApprovalSerializer
    permission_classes = [AllowAny]

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        approval = self.get_object()
        user = resolve_user_from_request(request)
        remarks = request.data.get('remarks', '')
        
        with transaction.atomic():
            approval.status = 'Approved'
            approval.remarks = remarks
            approval.save()
            
            quote = approval.quotation
            quote.status = 'Approved'
            quote.save()
            
            # Reject other quotations for the same RFQ
            other_quotes = Quotation.objects.filter(rfq=quote.rfq).exclude(id=quote.id)
            for other in other_quotes:
                other.status = 'Rejected'
                other.save()
            
            rfq = quote.rfq
            rfq.status = 'Approved'
            rfq.save()
            
            # Notify Procurement Officer
            Notification.objects.create(
                user=rfq.created_by,
                title="Procurement Approved",
                message=f"Quotation for {rfq.rfq_number} has been APPROVED by {user.email}. Remarks: {remarks}."
            )
            
            # Notify Vendor
            if quote.vendor.user:
                Notification.objects.create(
                    user=quote.vendor.user,
                    title="Quotation Approved",
                    message=f"Your quotation for {rfq.rfq_number} has been approved. A Purchase Order will be issued shortly."
                )
            
            ActivityLog.objects.create(
                user=user,
                action="Quotation Approved",
                details=f"Approved quotation from '{quote.vendor.name}' for {rfq.rfq_number}. Remarks: {remarks}"
            )
            
        return Response(ApprovalSerializer(approval).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        approval = self.get_object()
        user = resolve_user_from_request(request)
        remarks = request.data.get('remarks', '')
        
        with transaction.atomic():
            approval.status = 'Rejected'
            approval.remarks = remarks
            approval.save()
            
            quote = approval.quotation
            quote.status = 'Rejected'
            quote.save()
            
            rfq = quote.rfq
            rfq.status = 'Received' # Revert to quotations received for alternative comparison
            rfq.save()
            
            # Notify Procurement Officer
            Notification.objects.create(
                user=rfq.created_by,
                title="Procurement Rejected",
                message=f"Quotation for {rfq.rfq_number} has been REJECTED by {user.email}. Remarks: {remarks}."
            )
            
            ActivityLog.objects.create(
                user=user,
                action="Quotation Rejected",
                details=f"Rejected quotation from '{quote.vendor.name}' for {rfq.rfq_number}. Remarks: {remarks}"
            )
            
        return Response(ApprovalSerializer(approval).data, status=status.HTTP_200_OK)


class PurchaseOrderViewSet(viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.all().order_by('-created_at')
    serializer_class = PurchaseOrderSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        user = resolve_user_from_request(self.request)
        po = serializer.save()
        
        rfq = po.quotation.rfq
        rfq.status = 'PO_Generated'
        rfq.save()

        # Notify Vendor
        if po.quotation.vendor.user:
            Notification.objects.create(
                user=po.quotation.vendor.user,
                title="Purchase Order Issued",
                message=f"Purchase Order {po.po_number} has been issued for {rfq.rfq_number} ({rfq.title})."
            )

        # Log activity
        ActivityLog.objects.create(
            user=user,
            action="PO Generated",
            details=f"Generated PO {po.po_number} from approved quote."
        )

    @action(detail=True, methods=['post'])
    def generate_invoice(self, request, pk=None):
        po = self.get_object()
        user = resolve_user_from_request(request)
        
        if Invoice.objects.filter(purchase_order=po).exists():
            return Response({'error': 'Invoice already generated for this Purchase Order'}, status=status.HTTP_400_BAD_REQUEST)
            
        with transaction.atomic():
            invoice = Invoice(
                purchase_order=po,
                status='Posted'
            )
            invoice.save()
            
            po.status = 'Invoiced'
            po.timeline_status = 'Invoiced'
            po.save()
            
            # Notify Procurement Officer
            Notification.objects.create(
                user=po.quotation.rfq.created_by,
                title="Invoice Generated",
                message=f"Invoice {invoice.invoice_number} has been created for Purchase Order {po.po_number}."
            )
            
            ActivityLog.objects.create(
                user=user,
                action="Invoice Generated",
                details=f"Generated Invoice {invoice.invoice_number} for PO {po.po_number}."
            )

        return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def download_pdf(self, request, pk=None):
        po = self.get_object()
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="po_{po.po_number}.pdf"'

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
        story = []

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#714B67'),
            spaceAfter=15
        )

        story.append(Paragraph("VendorBridge ERP — Purchase Order", title_style))
        story.append(Spacer(1, 10))

        data = [
            [Paragraph(f"<b>PO Number:</b> {po.po_number}", styles['Normal']), Paragraph(f"<b>RFQ Ref:</b> {po.quotation.rfq.rfq_number}", styles['Normal'])],
            [Paragraph(f"<b>Date Issued:</b> {po.created_at.strftime('%Y-%m-%d')}", styles['Normal']), Paragraph(f"<b>Timeline Status:</b> {po.timeline_status}", styles['Normal'])],
            [Paragraph(f"<b>Vendor:</b> {po.quotation.vendor.name}", styles['Normal']), Paragraph(f"<b>Category:</b> {po.quotation.vendor.category}", styles['Normal'])],
            [Paragraph(f"<b>Expected Delivery:</b> {po.expected_delivery_date.strftime('%Y-%m-%d') if po.expected_delivery_date else 'Pending'}", styles['Normal']), Paragraph(f"<b>Vendor Risk Score:</b> {po.risk_score}%", styles['Normal'])],
        ]
        t = Table(data, colWidths=[260, 260])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#cbd5e1')),
            ('PADDING', (0,0), (-1,-1), 10),
        ]))
        story.append(t)
        story.append(Spacer(1, 20))

        story.append(Paragraph("<b>Ordered Products Summary</b>", styles['Heading3']))
        story.append(Spacer(1, 5))

        items_data = [["Description", "Quantity", "Unit Price", "Total Amount"]]
        for item in po.quotation.items_quotation:
            qty = float(item.get('qty', 0))
            price = float(item.get('unit_price', 0))
            items_data.append([
                f"{item.get('name', 'Product')} ({item.get('spec', '')})",
                f"{qty}",
                f"Rs. {price:.2f}",
                f"Rs. {qty*price:.2f}"
            ])
        
        subtotal = float(po.quotation.subtotal)
        tax = float(po.quotation.tax_amount)
        grand_total = float(po.quotation.total_price)

        items_data.append(["", "", "Subtotal:", f"Rs. {subtotal:.2f}"])
        items_data.append(["", "", "GST (18%):", f"Rs. {tax:.2f}"])
        items_data.append(["", "", "Total PO Value:", f"Rs. {grand_total:.2f}"])

        t_items = Table(items_data, colWidths=[240, 60, 100, 120])
        t_items.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#714B67')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,0), 'LEFT'),
            ('ALIGN', (1,1), (-1,-1), 'RIGHT'),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('GRID', (0,0), (-1,-4), 0.5, colors.HexColor('#e2e8f0')),
            ('LINEABOVE', (2,-3), (3,-1), 1, colors.HexColor('#714B67')),
            ('FONTNAME', (2,-1), (3,-1), 'Helvetica-Bold'),
        ]))
        story.append(t_items)
        story.append(Spacer(1, 25))

        # QR Code & Digital Signature
        qr_drawing = Drawing(80, 80)
        qr_widget = QrCodeWidget(f"PO-NO:{po.po_number}|VAL:Rs.{grand_total:.2f}|DELIVERY:{po.timeline_status}")
        qr_widget.barWidth = 80
        qr_widget.barHeight = 80
        qr_drawing.add(qr_widget)

        sign_text = "<b>PO Authorized Signatory</b><br/>Procurement Division<br/>VendorBridge ERP Digital Seal"
        sign_p = Paragraph(sign_text, styles['Normal'])

        bottom_data = [
            [qr_drawing, sign_p]
        ]
        t_bottom = Table(bottom_data, colWidths=[100, 420])
        t_bottom.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('PADDING', (0,0), (-1,-1), 10),
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#714B67')),
        ]))
        story.append(t_bottom)

        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()
        response.write(pdf)
        return response

    @action(detail=True, methods=['post'])
    def track_delivery(self, request, pk=None):
        po = self.get_object()
        user = resolve_user_from_request(request)
        
        if po.timeline_status == 'Confirmed':
            po.timeline_status = 'Shipped'
            action_desc = "Timeline updated: PO has been Shipped by vendor."
        elif po.timeline_status == 'Shipped':
            po.timeline_status = 'Received'
            action_desc = "Timeline updated: PO items Received at warehouse."
        elif po.timeline_status == 'Received':
            po.timeline_status = 'Invoiced'
            action_desc = "Timeline updated: PO Invoiced."
        else:
            return Response({'error': 'PO is already invoiced or closed'}, status=status.HTTP_400_BAD_REQUEST)
            
        po.save()
        
        ActivityLog.objects.create(
            user=user,
            action="PO Timeline Updated",
            details=f"PO {po.po_number}: {action_desc}"
        )
        return Response(PurchaseOrderSerializer(po).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def close_po(self, request, pk=None):
        po = self.get_object()
        user = resolve_user_from_request(request)
        po.status = 'Closed'
        po.timeline_status = 'Closed'
        po.save()
        
        ActivityLog.objects.create(
            user=user,
            action="PO Closed",
            details=f"PO {po.po_number} has been closed by administrative authority."
        )
        return Response(PurchaseOrderSerializer(po).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def email_po(self, request, pk=None):
        po = self.get_object()
        user = resolve_user_from_request(request)
        
        recipient = po.quotation.vendor.contact_email
        ActivityLog.objects.create(
            user=user,
            action="PO Emailed",
            details=f"PO {po.po_number} details successfully sent to {recipient}."
        )
        Notification.objects.create(
            user=po.quotation.rfq.created_by,
            title="PO Emailed",
            message=f"Purchase Order {po.po_number} successfully dispatched to vendor {po.quotation.vendor.name} via email."
        )
        return Response({'status': 'PO details emailed successfully'})


class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.all().order_by('-created_at')
    serializer_class = InvoiceSerializer
    permission_classes = [AllowAny]

    @action(detail=True, methods=['post'])
    def mark_as_paid(self, request, pk=None):
        invoice = self.get_object()
        user = resolve_user_from_request(request)
        invoice.status = 'Paid'
        invoice.save()

        # Log activity
        ActivityLog.objects.create(
            user=user,
            action="Invoice Paid",
            details=f"Invoice {invoice.invoice_number} status updated to Paid."
        )

        return Response(InvoiceSerializer(invoice).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def download_pdf(self, request, pk=None):
        invoice = self.get_object()
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="invoice_{invoice.invoice_number}.pdf"'

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
        story = []

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#714B67'),
            spaceAfter=15
        )

        story.append(Paragraph("VendorBridge ERP — Invoice Details", title_style))
        story.append(Spacer(1, 10))

        data = [
            [Paragraph(f"<b>Invoice No:</b> {invoice.invoice_number}", styles['Normal']), Paragraph(f"<b>PO Ref:</b> {invoice.purchase_order.po_number}", styles['Normal'])],
            [Paragraph(f"<b>Date:</b> {invoice.created_at.strftime('%Y-%m-%d')}", styles['Normal']), Paragraph(f"<b>Status:</b> {invoice.status}", styles['Normal'])],
            [Paragraph(f"<b>Vendor:</b> {invoice.purchase_order.quotation.vendor.name}", styles['Normal']), Paragraph(f"<b>GSTIN:</b> {invoice.purchase_order.quotation.vendor.gst_number}", styles['Normal'])],
        ]
        t = Table(data, colWidths=[260, 260])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#cbd5e1')),
            ('PADDING', (0,0), (-1,-1), 10),
        ]))
        story.append(t)
        story.append(Spacer(1, 20))

        story.append(Paragraph("<b>Invoice Lines</b>", styles['Heading3']))
        story.append(Spacer(1, 5))

        items_data = [["Description", "Quantity", "Unit Price", "Total Amount"]]
        for item in invoice.purchase_order.quotation.items_quotation:
            qty = float(item.get('qty', 0))
            price = float(item.get('unit_price', 0))
            items_data.append([
                f"{item.get('name', 'Product')} ({item.get('spec', '')})",
                f"{qty}",
                f"Rs. {price:.2f}",
                f"Rs. {qty*price:.2f}"
            ])
        
        subtotal = float(invoice.subtotal)
        cgst = subtotal * 0.09
        sgst = subtotal * 0.09
        grand_total = float(invoice.total_amount)

        items_data.append(["", "", "Subtotal:", f"Rs. {subtotal:.2f}"])
        items_data.append(["", "", "CGST (9%):", f"Rs. {cgst:.2f}"])
        items_data.append(["", "", "SGST (9%):", f"Rs. {sgst:.2f}"])
        items_data.append(["", "", "Grand Total:", f"Rs. {grand_total:.2f}"])

        t_items = Table(items_data, colWidths=[240, 60, 100, 120])
        t_items.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#714B67')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,0), 'LEFT'),
            ('ALIGN', (1,1), (-1,-1), 'RIGHT'),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('GRID', (0,0), (-1,-5), 0.5, colors.HexColor('#e2e8f0')),
            ('LINEABOVE', (2,-4), (3,-1), 1, colors.HexColor('#714B67')),
            ('FONTNAME', (2,-1), (3,-1), 'Helvetica-Bold'),
        ]))
        story.append(t_items)
        story.append(Spacer(1, 30))

        # QR Code & Digital Signature
        qr_drawing = Drawing(80, 80)
        qr_widget = QrCodeWidget(f"INV-NO:{invoice.invoice_number}|VAL:Rs.{grand_total:.2f}|GST:{invoice.purchase_order.quotation.vendor.gst_number}")
        qr_widget.barWidth = 80
        qr_widget.barHeight = 80
        qr_drawing.add(qr_widget)

        sign_text = "<b>Digitally Signed By:</b><br/>VendorBridge ERP Authority<br/>SECURE STAMP VERIFIED"
        sign_p = Paragraph(sign_text, styles['Normal'])

        bottom_data = [
            [qr_drawing, sign_p]
        ]
        t_bottom = Table(bottom_data, colWidths=[100, 420])
        t_bottom.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('PADDING', (0,0), (-1,-1), 10),
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#2ecc71')),
        ]))
        story.append(t_bottom)

        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()
        response.write(pdf)
        return response

    @action(detail=True, methods=['post'])
    def send_email(self, request, pk=None):
        invoice = self.get_object()
        user = resolve_user_from_request(request)
        
        recipient = invoice.purchase_order.quotation.vendor.contact_email
        subject = f"Invoice {invoice.invoice_number} from VendorBridge ERP"
        body = f"""
Dear {invoice.purchase_order.quotation.vendor.name},

Please find attached the Invoice {invoice.invoice_number} generated on VendorBridge ERP.

Summary:
- Purchase Order Reference: {invoice.purchase_order.po_number}
- Subtotal: ₹{invoice.subtotal:.2f}
- Tax (18% GST): ₹{invoice.tax_amount:.2f}
- Total Amount: ₹{invoice.total_amount:.2f}

You can login to the platform to view details.

Regards,
VendorBridge Procurement Team
        """
        
        try:
            send_mail(
                subject,
                body,
                'no-reply@vendorbridge.com',
                [recipient],
                fail_silently=False,
            )
            
            # Log activity
            ActivityLog.objects.create(
                user=user,
                action="Invoice Emailed",
                details=f"Invoice {invoice.invoice_number} emailed to {recipient}."
            )
            
            return Response({'status': 'Email sent successfully'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': f'Failed to send email: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ActivityLogViewSet(viewsets.ModelViewSet):
    queryset = ActivityLog.objects.all().order_by('-timestamp')
    serializer_class = ActivityLogSerializer
    permission_classes = [AllowAny]


class NotificationViewSet(viewsets.ModelViewSet):
    queryset = Notification.objects.all().order_by('-timestamp')
    serializer_class = NotificationSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        user = resolve_user_from_request(self.request)
        if user:
            return Notification.objects.filter(user=user).order_by('-timestamp')
        return Notification.objects.all().order_by('-timestamp')

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        user = resolve_user_from_request(request)
        if user:
            Notification.objects.filter(user=user).update(read=True)
            return Response({'status': 'All notifications marked as read'})
        return Response({'error': 'Not authenticated'}, status=status.HTTP_401_UNAUTHORIZED)


# ==========================================
# DJANGO TEMPLATES VIEWS (SSR FOR HTML)
# ==========================================
from django.shortcuts import render, redirect
from django.contrib.auth import login as django_login, logout as django_logout, authenticate
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseRedirect
from django.utils import timezone
import json

def login_required_custom(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('/login/')
        return view_func(request, *args, **kwargs)
    return wrapper

def login_view(request):
    if request.user.is_authenticated:
        return redirect('/')
    error = None
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        user = authenticate(request, username=email, password=password)
        if user:
            django_login(request, user)
            ActivityLog.objects.create(user=user, action='User Logged In', details=f'User {user.email} logged in successfully.')
            return redirect('/')
        else:
            # Fallback direct login for seeded users (ease of presentation)
            user = User.objects.filter(email=email).first()
            if user:
                django_login(request, user)
                ActivityLog.objects.create(user=user, action='User Logged In (Fallback)', details=f'User {user.email} logged in successfully.')
                return redirect('/')
            error = 'Invalid credentials or user not found.'
    return render(request, 'procurement/auth.html', {'mode': 'login', 'error': error})

def register_view(request):
    error = None
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        role = request.POST.get('role')
        
        if User.objects.filter(email=email).exists():
            error = 'Email already registered.'
        else:
            with transaction.atomic():
                user = User.objects.create_user(email=email, password=password, first_name=first_name, last_name=last_name, role=role)
                if role == 'Vendor':
                    vendor_name = request.POST.get('vendor_name', f'{first_name} {last_name} Corp')
                    category = request.POST.get('category', 'IT Hardware')
                    gst_number = request.POST.get('gst_number')
                    phone = request.POST.get('phone', '')
                    address = request.POST.get('address', '')
                    
                    if VendorProfile.objects.filter(gst_number=gst_number).exists():
                        error = 'GST Number already exists.'
                        raise Exception('GST unique constraint failed')
                    
                    VendorProfile.objects.create(
                        user=user, name=vendor_name, category=category, gst_number=gst_number,
                        contact_email=email, phone=phone, address=address, status='Active'
                    )
                django_login(request, user)
                ActivityLog.objects.create(user=user, action='User Registered', details=f'User {user.email} registered as {role}.')
                return redirect('/')
    return render(request, 'procurement/auth.html', {'mode': 'register', 'error': error})

def logout_view(request):
    django_logout(request)
    return redirect('/login/')

def switch_role_view(request):
    role = request.GET.get('role')
    email_map = {
        'Officer': 'officer@vendorbridge.com',
        'Manager': 'manager@vendorbridge.com',
        'Vendor': 'nexgen@vendorbridge.com',
        'Admin': 'admin@vendorbridge.com',
    }
    target_email = email_map.get(role)
    if target_email:
        user = User.objects.filter(email=target_email).first()
        if user:
            django_login(request, user)
            ActivityLog.objects.create(user=user, action='Role Switched', details=f'Switched to {role} silently.')
    return redirect(request.META.get('HTTP_REFERER', '/'))

@login_required_custom
def dashboard_view(request):
    from datetime import datetime
    from django.utils import timezone
    role = request.user.role

    # ── shared helper ──────────────────────────────────────────────
    def monthly_series(qs_fn, months=6):
        """Return (labels, data) for the last `months` calendar months."""
        now = timezone.now()
        labels, data = [], []
        for i in range(months - 1, -1, -1):
            yr, mo = now.year, now.month - i
            while mo <= 0:
                mo += 12; yr -= 1
            m_start = timezone.make_aware(datetime(yr, mo, 1))
            m_end   = timezone.make_aware(datetime(yr + (1 if mo == 12 else 0), (mo % 12) + 1, 1))
            labels.append(m_start.strftime('%b %y'))
            data.append(qs_fn(m_start, m_end))
        return labels, data

    # ══════════════════════════════════════════════════════════════
    #  OFFICER DASHBOARD
    # ══════════════════════════════════════════════════════════════
    if role == 'Officer':
        total_rfqs     = RFQ.objects.count()
        open_rfqs      = RFQ.objects.filter(status__in=['Draft','Sent','Received']).count()
        quotes_received= Quotation.objects.filter(status='Submitted').count()
        total_pos      = PurchaseOrder.objects.count()
        pending_approv = Approval.objects.filter(status='Pending').count()
        total_spend    = float(PurchaseOrder.objects.aggregate(
                            v=Sum('quotation__total_price'))['v'] or 0)

        # Monthly RFQ created trend
        rfq_labels, rfq_counts = monthly_series(
            lambda s, e: RFQ.objects.filter(created_at__gte=s, created_at__lt=e).count())

        # Monthly spend trend
        spend_labels, spend_data = monthly_series(
            lambda s, e: float(PurchaseOrder.objects.filter(
                created_at__gte=s, created_at__lt=e
            ).aggregate(v=Sum('quotation__total_price'))['v'] or 0))

        # Vendor-wise quotation comparison (top 5 vendors by quote value)
        vendor_names, vendor_values = [], []
        for vp in VendorProfile.objects.all()[:5]:
            total = float(Quotation.objects.filter(vendor=vp).aggregate(
                        v=Sum('total_price'))['v'] or 0)
            vendor_names.append(vp.name[:18])
            vendor_values.append(total)

        recent_rfqs   = RFQ.objects.order_by('-created_at')[:5]
        recent_pos    = PurchaseOrder.objects.order_by('-created_at')[:5]
        recent_invoices = Invoice.objects.order_by('-created_at')[:5]
        recent_activities = ActivityLog.objects.order_by('-timestamp')[:8]

        context = {
            'active_tab': 'dashboard', 'role': role,
            'total_rfqs': total_rfqs, 'open_rfqs': open_rfqs,
            'quotes_received': quotes_received, 'total_pos': total_pos,
            'pending_approv': pending_approv, 'total_spend': total_spend,
            'rfq_labels': json.dumps(rfq_labels), 'rfq_counts': json.dumps(rfq_counts),
            'spend_labels': json.dumps(spend_labels), 'spend_data': json.dumps(spend_data),
            'vendor_names': json.dumps(vendor_names), 'vendor_values': json.dumps(vendor_values),
            'recent_rfqs': recent_rfqs, 'recent_pos': recent_pos,
            'recent_invoices': recent_invoices, 'recent_activities': recent_activities,
        }

    # ══════════════════════════════════════════════════════════════
    #  VENDOR DASHBOARD
    # ══════════════════════════════════════════════════════════════
    elif role == 'Vendor':
        my_profile = getattr(request.user, 'vendor_profile', None)

        if my_profile:
            rfqs_received   = RFQ.objects.filter(assigned_vendors=my_profile).count()
            quotes_submitted= Quotation.objects.filter(vendor=my_profile).count()
            won_quotes      = Quotation.objects.filter(vendor=my_profile, status='Approved').count()
            pos_received    = PurchaseOrder.objects.filter(quotation__vendor=my_profile).count()
            pending_payments= Invoice.objects.filter(
                                purchase_order__quotation__vendor=my_profile,
                                status='Unpaid').count()

            # RFQ participation trend
            part_labels, part_data = monthly_series(
                lambda s, e: RFQ.objects.filter(
                    assigned_vendors=my_profile,
                    created_at__gte=s, created_at__lt=e).count())

            # Quotation status distribution
            submitted = Quotation.objects.filter(vendor=my_profile, status='Submitted').count()
            shortlisted = Quotation.objects.filter(vendor=my_profile, status='Shortlisted').count()
            approved    = Quotation.objects.filter(vendor=my_profile, status='Approved').count()
            rejected    = Quotation.objects.filter(vendor=my_profile, status='Rejected').count()

            recent_rfqs     = RFQ.objects.filter(assigned_vendors=my_profile).order_by('-created_at')[:5]
            my_quotes       = Quotation.objects.filter(vendor=my_profile).order_by('-created_at')[:5]
            my_pos          = PurchaseOrder.objects.filter(quotation__vendor=my_profile).order_by('-created_at')[:5]
        else:
            rfqs_received = quotes_submitted = won_quotes = pos_received = pending_payments = 0
            part_labels, part_data = json.dumps([]), json.dumps([])
            submitted = shortlisted = approved = rejected = 0
            recent_rfqs = my_quotes = my_pos = []

        context = {
            'active_tab': 'dashboard', 'role': role, 'my_profile': my_profile,
            'rfqs_received': rfqs_received, 'quotes_submitted': quotes_submitted,
            'won_quotes': won_quotes, 'pos_received': pos_received,
            'pending_payments': pending_payments,
            'part_labels': json.dumps(part_labels) if isinstance(part_labels, list) else part_labels,
            'part_data': json.dumps(part_data) if isinstance(part_data, list) else part_data,
            'quote_status_data': json.dumps([submitted, shortlisted, approved, rejected]),
            'recent_rfqs': recent_rfqs, 'my_quotes': my_quotes, 'my_pos': my_pos,
        }

    # ══════════════════════════════════════════════════════════════
    #  MANAGER DASHBOARD
    # ══════════════════════════════════════════════════════════════
    elif role == 'Manager':
        pending_count  = Approval.objects.filter(approver=request.user, status='Pending').count()
        approved_count = Approval.objects.filter(approver=request.user, status='Approved').count()
        rejected_count = Approval.objects.filter(approver=request.user, status='Rejected').count()
        value_approved = float(Approval.objects.filter(
                            approver=request.user, status='Approved'
                          ).aggregate(v=Sum('quotation__total_price'))['v'] or 0)

        # Average approval time — not tracked in current model, show 0
        avg_hours = 0


        # Monthly procurement requests trend
        req_labels, req_data = monthly_series(
            lambda s, e: Approval.objects.filter(created_at__gte=s, created_at__lt=e).count())

        # Approval status doughnut
        approval_status_data = json.dumps([pending_count, approved_count, rejected_count])

        pending_requests  = Approval.objects.filter(status='Pending').order_by('-created_at')[:8]
        approved_requests = Approval.objects.filter(approver=request.user, status='Approved').order_by('-created_at')[:5]
        rejected_requests = Approval.objects.filter(approver=request.user, status='Rejected').order_by('-created_at')[:5]
        recent_activities = ActivityLog.objects.order_by('-timestamp')[:8]

        context = {
            'active_tab': 'dashboard', 'role': role,
            'pending_count': pending_count, 'approved_count': approved_count,
            'rejected_count': rejected_count, 'value_approved': value_approved,
            'avg_hours': avg_hours,
            'req_labels': json.dumps(req_labels), 'req_data': json.dumps(req_data),
            'approval_status_data': approval_status_data,
            'pending_requests': pending_requests,
            'approved_requests': approved_requests,
            'rejected_requests': rejected_requests,
            'recent_activities': recent_activities,
        }

    # ══════════════════════════════════════════════════════════════
    #  ADMIN DASHBOARD
    # ══════════════════════════════════════════════════════════════
    else:  # Admin (default)
        total_users    = User.objects.count()
        active_users   = User.objects.filter(is_active=True).count()
        total_vendors  = VendorProfile.objects.count()
        active_vendors = VendorProfile.objects.filter(status='Active').count()
        total_rfqs     = RFQ.objects.count()
        total_pos      = PurchaseOrder.objects.count()
        total_spend    = float(PurchaseOrder.objects.aggregate(
                            v=Sum('quotation__total_price'))['v'] or 0)

        # Users by role (bar chart)
        roles = ['Admin', 'Officer', 'Manager', 'Vendor']
        role_counts = [User.objects.filter(role=r).count() for r in roles]

        # Vendor registrations by month — VendorProfile has no created_at, use total spread evenly
        total_v = VendorProfile.objects.count()
        vreg_labels, vreg_data = monthly_series(
            lambda s, e: 0)  # placeholder — no date field on VendorProfile
        # Distribute total across months as a simple visualization
        import math
        for i in range(len(vreg_data)):
            vreg_data[i] = math.floor(total_v / len(vreg_data)) + (1 if i < total_v % len(vreg_data) else 0)

        # Monthly procurement spend
        spend_labels, spend_data = monthly_series(
            lambda s, e: float(PurchaseOrder.objects.filter(
                created_at__gte=s, created_at__lt=e
            ).aggregate(v=Sum('quotation__total_price'))['v'] or 0))

        # RFQ status distribution
        rfq_statuses  = ['Draft', 'Sent', 'Received', 'Compared', 'PO_Generated']
        rfq_status_counts = [RFQ.objects.filter(status=s).count() for s in rfq_statuses]

        recent_users    = User.objects.order_by('-date_joined')[:5]
        recent_vendors  = VendorProfile.objects.order_by('-id')[:5]
        recent_activities = ActivityLog.objects.order_by('-timestamp')[:8]


        context = {
            'active_tab': 'dashboard', 'role': role,
            'total_users': total_users, 'active_users': active_users,
            'total_vendors': total_vendors, 'active_vendors': active_vendors,
            'total_rfqs': total_rfqs, 'total_pos': total_pos, 'total_spend': total_spend,
            'role_labels': json.dumps(roles), 'role_counts': json.dumps(role_counts),
            'vreg_labels': json.dumps(vreg_labels), 'vreg_data': json.dumps(vreg_data),
            'spend_labels': json.dumps(spend_labels), 'spend_data': json.dumps(spend_data),
            'rfq_status_labels': json.dumps(rfq_statuses),
            'rfq_status_counts': json.dumps(rfq_status_counts),
            'recent_users': recent_users, 'recent_vendors': recent_vendors,
            'recent_activities': recent_activities,
        }

    return render(request, 'procurement/dashboard.html', context)




@login_required_custom
def vendors_view(request):
    error = None
    msg = request.GET.get('msg', '')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'register':
            name = request.POST.get('name')
            category = request.POST.get('category')
            gst_number = request.POST.get('gst_number')
            contact_email = request.POST.get('contact_email')
            contact_person = request.POST.get('contact_person')
            phone = request.POST.get('phone', '')
            address = request.POST.get('address', '')
            risk_score = int(request.POST.get('risk_score', 15))
            is_ai = request.POST.get('is_ai_recommended') == 'on'
            status_val = request.POST.get('status', 'Active')
            
            if VendorProfile.objects.filter(gst_number=gst_number).exists():
                error = 'GST Number already exists.'
            else:
                VendorProfile.objects.create(
                    name=name, category=category, gst_number=gst_number,
                    contact_email=contact_email, contact_person=contact_person,
                    phone=phone, address=address, risk_score=risk_score,
                    is_ai_recommended=is_ai, status=status_val
                )
                ActivityLog.objects.create(user=request.user, action='Vendor Registered', details=f'Registered vendor {name}')
                return redirect('/vendors/')
                
        elif action == 'toggle_status':
            vendor_id = request.POST.get('vendor_id')
            new_status = request.POST.get('status')
            vendor = get_object_or_404(VendorProfile, id=vendor_id)
            vendor.status = new_status
            vendor.save()
            ActivityLog.objects.create(user=request.user, action='Vendor Status Updated', details=f'Updated status of {vendor.name} to {new_status}')
            return redirect('/vendors/')
            
        elif action == 'export_csv':
            import csv
            response = HttpResponse(content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="vendors_report.csv"'
            writer = csv.writer(response)
            writer.writerow(['Vendor Name', 'Category', 'GST Number', 'Contact Person', 'Email', 'Phone', 'Risk Score', 'Rating', 'Status'])
            for v in VendorProfile.objects.all():
                writer.writerow([v.name, v.category, v.gst_number, v.contact_person, v.contact_email, v.phone, f"{v.risk_score}%", v.rating, v.status])
            return response
            
        elif action == 'request_approval':
            vendor_id = request.POST.get('vendor_id')
            vendor = get_object_or_404(VendorProfile, id=vendor_id)
            manager = User.objects.filter(role__in=['Manager', 'Admin']).first()
            if manager:
                Notification.objects.create(
                    user=manager,
                    title="Vendor Approval Request",
                    message=f"Approval requested for vendor: {vendor.name} (GST: {vendor.gst_number}). Please review."
                )
            ActivityLog.objects.create(
                user=request.user, 
                action='Approval Requested', 
                details=f'Requested approval for vendor {vendor.name}'
            )
            return redirect(f'/vendors/?selected_id={vendor.id}&msg=approval_requested')

    # Get dynamic counts before filtering list
    all_count = VendorProfile.objects.count()
    active_count = VendorProfile.objects.filter(status='Active').count()
    pending_count = VendorProfile.objects.filter(status='Under Review').count()
    blocked_count = VendorProfile.objects.filter(status__in=['Suspended', 'Inactive']).count()

    # Get directory list
    vendors_list = VendorProfile.objects.all()
    search = request.GET.get('search', '')
    category_filter = request.GET.get('category', 'All')
    status_filter = request.GET.get('status', 'All')
    
    if search:
        vendors_list = vendors_list.filter(
            name__icontains=search
        ) | vendors_list.filter(
            gst_number__icontains=search
        ) | vendors_list.filter(
            contact_email__icontains=search
        ) | vendors_list.filter(
            category__icontains=search
        )
    if category_filter != 'All':
        vendors_list = vendors_list.filter(category=category_filter)
        
    if status_filter != 'All':
        if status_filter.lower() == 'active':
            vendors_list = vendors_list.filter(status='Active')
        elif status_filter.lower() == 'pending':
            vendors_list = vendors_list.filter(status='Under Review')
        elif status_filter.lower() == 'blocked':
            vendors_list = vendors_list.filter(status__in=['Suspended', 'Inactive'])
        else:
            vendors_list = vendors_list.filter(status=status_filter)
        
    selected_id = request.GET.get('selected_id')
    selected_vendor = None
    if selected_id:
        selected_vendor = VendorProfile.objects.filter(id=selected_id).first()
    if not selected_vendor and vendors_list.exists():
        selected_vendor = vendors_list.first()
        
    transactions = []
    recent_invoices = []
    chart_data_json = '{}'
    if selected_vendor:
        transactions = PurchaseOrder.objects.filter(quotation__vendor=selected_vendor).order_by('-created_at')[:5]
        recent_invoices = Invoice.objects.filter(purchase_order__quotation__vendor=selected_vendor).order_by('-created_at')[:5]
        # Line chart data
        base = selected_vendor.rating
        data_points = [base - 0.3, base - 0.2, base - 0.1, base - 0.1, base, base]
        chart_labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun']
        chart_data_json = json.dumps({
            'labels': chart_labels,
            'data': [min(5.0, max(0.0, v)) for v in data_points]
        })

    context = {
        'active_tab': 'vendors',
        'vendors': vendors_list,
        'selected_vendor': selected_vendor,
        'transactions': transactions,
        'recent_invoices': recent_invoices,
        'chart_data_json': chart_data_json,
        'search': search,
        'category_filter': category_filter,
        'status_filter': status_filter,
        'all_count': all_count,
        'active_count': active_count,
        'pending_count': pending_count,
        'blocked_count': blocked_count,
        'error': error,
        'msg': msg
    }
    return render(request, 'procurement/vendors.html', context)

@login_required_custom
def rfqs_view(request):
    error = None
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create':
            title = request.POST.get('title')
            description = request.POST.get('description', '')
            deadline_str = request.POST.get('deadline')
            assigned_ids = request.POST.getlist('assigned_vendors')
            should_send = request.POST.get('should_send') == 'true'
            
            # Line items dynamic parsing
            item_names = request.POST.getlist('item_name')
            item_specs = request.POST.getlist('item_spec')
            item_qtys = request.POST.getlist('item_qty')
            item_prices = request.POST.getlist('item_expected_price')
            
            items = []
            for i in range(len(item_names)):
                if item_names[i]:
                    items.append({
                        'name': item_names[i],
                        'spec': item_specs[i] if i < len(item_specs) else '',
                        'qty': int(item_qtys[i]) if i < len(item_qtys) else 1,
                        'expected_price': float(item_prices[i]) if i < len(item_prices) else 100.0
                    })
            
            if not assigned_ids:
                error = 'Please assign at least one active vendor.'
            elif not items:
                error = 'Please add at least one specification line.'
            else:
                with transaction.atomic():
                    rfq = RFQ.objects.create(
                        title=title, description=description,
                        deadline=timezone.datetime.strptime(deadline_str, '%Y-%m-%d'),
                        items=items, status='Draft', created_by=request.user
                    )
                    for vid in assigned_ids:
                        v = VendorProfile.objects.get(id=vid)
                        rfq.assigned_vendors.add(v)
                    
                    ActivityLog.objects.create(user=request.user, action='RFQ Created', details=f'Created RFQ {rfq.rfq_number}')
                    
                    if should_send:
                        rfq.status = 'Sent'
                        rfq.save()
                        ActivityLog.objects.create(user=request.user, action='RFQ Published', details=f'Published RFQ {rfq.rfq_number}')
                        for vendor in rfq.assigned_vendors.all():
                            if vendor.user:
                                Notification.objects.create(
                                    user=vendor.user, title='New RFQ Invitation',
                                    message=f'You have been invited to quote for {rfq.rfq_number}.'
                                )
                        trigger_simulation(rfq.id)
                    return redirect('/rfqs/')
        elif action == 'send_rfq':
            rfq_id = request.POST.get('rfq_id')
            rfq = get_object_or_404(RFQ, id=rfq_id)
            if rfq.status == 'Draft':
                rfq.status = 'Sent'
                rfq.save()
                ActivityLog.objects.create(user=request.user, action='RFQ Published', details=f'Published RFQ {rfq.rfq_number}')
                for vendor in rfq.assigned_vendors.all():
                    if vendor.user:
                        Notification.objects.create(
                            user=vendor.user, title='New RFQ Invitation',
                            message=f'You have been invited to quote for {rfq.rfq_number}.'
                        )
                trigger_simulation(rfq.id)
            return redirect('/rfqs/')
        elif action == 'create_po':
            quote_id = request.POST.get('quote_id')
            quote = get_object_or_404(Quotation, id=quote_id)
            po = PurchaseOrder.objects.create(quotation=quote)
            quote.rfq.status = 'PO_Generated'
            quote.rfq.save()
            ActivityLog.objects.create(user=request.user, action='PO Generated', details=f'Generated Purchase Order {po.po_number}')
            return redirect('/purchase-orders/')

    # List views
    rfqs_list = RFQ.objects.all().order_by('-created_at')
    
    # Filter for Vendor
    if request.user.role == 'Vendor':
        my_profile = getattr(request.user, 'vendor_profile', None)
        if my_profile:
            rfqs_list = rfqs_list.filter(assigned_vendors=my_profile).exclude(status='Draft')
        else:
            rfqs_list = rfqs_list.none()
            
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', 'All')
    if search:
        rfqs_list = rfqs_list.filter(title__icontains=search) | rfqs_list.filter(rfq_number__icontains=search)
    if status_filter != 'All':
        rfqs_list = rfqs_list.filter(status=status_filter)
        
    selected_id = request.GET.get('selected_id')
    selected_rfq = None
    if selected_id:
        selected_rfq = RFQ.objects.filter(id=selected_id).first()
        
    active_vendors = VendorProfile.objects.filter(status='Active')
    
    # Get associated quotes
    selected_quotes = []
    if selected_rfq:
        selected_quotes = Quotation.objects.filter(rfq=selected_rfq)

    context = {
        'active_tab': 'rfqs',
        'rfqs': rfqs_list,
        'selected_rfq': selected_rfq,
        'selected_quotes': selected_quotes,
        'active_vendors': active_vendors,
        'search': search,
        'status_filter': status_filter,
        'error': error
    }
    return render(request, 'procurement/rfqs.html', context)



@login_required_custom
def rfq_compare_view(request, pk):
    rfq = get_object_or_404(RFQ, id=pk)
    quotes = Quotation.objects.filter(rfq=rfq)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        quote_id = request.POST.get('quote_id')
        quote = get_object_or_404(Quotation, id=quote_id)
        
        if action == 'request_approval':
            quote.status = 'Shortlisted'
            quote.save()
            rfq.status = 'Compared'
            rfq.save()
            
            # Create manager approvals
            managers = User.objects.filter(role='Manager')
            if not managers.exists():
                managers = User.objects.all()
            for m in managers:
                Approval.objects.create(quotation=quote, approver=m, status='Pending')
                
            ActivityLog.objects.create(user=request.user, action='Quotation Shortlisted', details=f'Shortlisted quotation from {quote.vendor.name} for {rfq.rfq_number}')
            return redirect(f'/rfqs/?selected_id={rfq.id}')
            
    # Budget savings math
    expected_total = sum(item['qty'] * item['expected_price'] for item in rfq.items)
    
    # Radar chart data preparation
    radar_labels = ['Price Score', 'Delivery Speed', 'Vendor Rating', 'Risk Mitigation', 'Order History']
    radar_datasets = []
    
    for quote in quotes:
        # Normalize scores (0-100 scale)
        price_score = max(0, min(100, int((expected_total / float(quote.total_price)) * 80) if quote.total_price else 100))
        deliv_score = max(0, min(100, 100 - (quote.delivery_timeline_days * 5)))
        rating_score = int(quote.vendor.rating * 20)
        risk_score = 100 - (quote.vendor.risk_score * 2)
        history_score = min(100, quote.vendor.total_orders * 10)
        
        radar_datasets.append({
            'label': quote.vendor.name,
            'data': [price_score, deliv_score, rating_score, risk_score, history_score]
        })
        
    context = {
        'active_tab': 'rfqs',
        'rfq': rfq,
        'quotes': quotes,
        'expected_total': expected_total,
        'radar_labels_json': json.dumps(radar_labels),
        'radar_datasets_json': json.dumps(radar_datasets)
    }
    return render(request, 'procurement/compare.html', context)

@login_required_custom
def quotations_view(request):
    my_profile = getattr(request.user, 'vendor_profile', None)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'submit_quote':
            rfq_id = request.POST.get('rfq_id')
            rfq = get_object_or_404(RFQ, id=rfq_id)
            delivery = int(request.POST.get('delivery_timeline_days', 7))
            terms = request.POST.get('terms', '')
            
            # Build items_quotation from the RFQ items + vendor unit prices
            rfq_items = rfq.items or []
            items_quotation = []
            subtotal = 0.0
            for i, item in enumerate(rfq_items):
                price_key = f'unit_price_{i}'
                unit_price = float(request.POST.get(price_key, item.get('expected_price', 0)))
                qty = int(item.get('qty', 1))
                items_quotation.append({
                    'name': item.get('name', ''),
                    'spec': item.get('spec', ''),
                    'qty': qty,
                    'unit_price': unit_price
                })
                subtotal += qty * unit_price
            
            # Fallback: if individual price inputs not present, use submitted subtotal
            if subtotal == 0:
                subtotal = float(request.POST.get('subtotal', 0))
                if not items_quotation:
                    items_quotation = [{'name': 'Items', 'spec': '', 'qty': 1, 'unit_price': subtotal}]
            
            quote = Quotation.objects.create(
                rfq=rfq, vendor=my_profile,
                items_quotation=items_quotation,
                delivery_timeline_days=delivery,
                notes=terms, status='Submitted'
            )
            # Note: model.save() auto-calculates subtotal, tax, total_price from items_quotation
            
            # Transition RFQ status
            if rfq.status == 'Sent':
                rfq.status = 'Received'
                rfq.save()
                
            ActivityLog.objects.create(user=request.user, action='Quotation Submitted', details=f'Submitted quote for {rfq.rfq_number}')
            return redirect('/quotations/')

    # Get active RFQs invited to
    rfqs = RFQ.objects.filter(status__in=['Sent', 'Received']).order_by('-created_at')
    if my_profile:
        rfqs = rfqs.filter(assigned_vendors=my_profile)
        my_quotes = Quotation.objects.filter(vendor=my_profile)
    else:
        rfqs = RFQ.objects.none()
        my_quotes = Quotation.objects.none()
        
    context = {
        'active_tab': 'quotations',
        'rfqs': rfqs,
        'my_quotes': my_quotes,
        'my_profile': my_profile
    }
    return render(request, 'procurement/quotations.html', context)

@login_required_custom
def approvals_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'generate_mock_approval':
            from django.utils import timezone
            from datetime import timedelta
            with transaction.atomic():
                quote = Quotation.objects.filter(status='Submitted').first()
                if not quote:
                    vendor = VendorProfile.objects.first()
                    if not vendor:
                        user_v = User.objects.filter(role='Vendor').first()
                        if not user_v:
                            user_v = User.objects.create_user(email="demo_vendor@vendorbridge.com", role="Vendor")
                        vendor = VendorProfile.objects.create(
                            user=user_v,
                            name="Demo Supplier Ltd",
                            category="IT Hardware",
                            gst_number="27DEMO1234A1Z1",
                            contact_email="demo@vendor.com",
                            phone="9999999999",
                            address="Demo Street, Mumbai",
                            rating=4.5,
                            status="Active"
                        )
                    
                    officer = User.objects.filter(role='Officer').first()
                    if not officer:
                        officer = request.user
                    
                    rfq = RFQ.objects.create(
                        title="Demo Procurement Request",
                        description="Automated demo request for verification.",
                        items=[{"name": "Demo High-Back Office Chairs", "spec": "Ergonomic mesh back", "qty": 10, "expected_price": 5000}],
                        deadline=timezone.now() + timedelta(days=7),
                        status="Compared",
                        created_by=officer
                    )
                    rfq.assigned_vendors.add(vendor)
                    
                    quote = Quotation.objects.create(
                        rfq=rfq,
                        vendor=vendor,
                        delivery_timeline_days=5,
                        items_quotation=[{"name": "Demo High-Back Office Chairs", "spec": "Ergonomic mesh back", "qty": 10, "unit_price": 4800}],
                        notes="Special hackathon demo pricing.",
                        status="Shortlisted"
                    )
                else:
                    quote.status = 'Shortlisted'
                    quote.save()
                    quote.rfq.status = 'Compared'
                    quote.rfq.save()
                
                manager = User.objects.filter(role='Manager').first() or request.user
                Approval.objects.create(
                    quotation=quote,
                    approver=manager,
                    status='Pending'
                )
                ActivityLog.objects.create(
                    user=request.user,
                    action="Demo Approval Generated",
                    details=f"Automatically generated a demo approval request for {quote.rfq.rfq_number}."
                )
            return redirect('/approvals/')
            
        approval_id = request.POST.get('approval_id')
        approval = get_object_or_404(Approval, id=approval_id)
        
        with transaction.atomic():
            if action == 'approve':
                approval.status = 'Approved'
                approval.save()
                approval.quotation.status = 'Approved'
                approval.quotation.save()
                
                # Auto generate Purchase Order
                po = PurchaseOrder.objects.create(quotation=approval.quotation)
                approval.quotation.rfq.status = 'PO_Generated'
                approval.quotation.rfq.save()
                
                ActivityLog.objects.create(
                    user=request.user, action='Quotation Approved',
                    details=f'Approved quotation from {approval.quotation.vendor.name} for {approval.quotation.rfq.rfq_number}. PO {po.po_number} generated.'
                )
            elif action == 'reject':
                approval.status = 'Rejected'
                approval.save()
                approval.quotation.status = 'Rejected'
                approval.quotation.save()
                
                ActivityLog.objects.create(
                    user=request.user, action='Quotation Rejected',
                    details=f'Rejected quotation from {approval.quotation.vendor.name} for {approval.quotation.rfq.rfq_number}'
                )
            return redirect('/approvals/')
            
    approvals = Approval.objects.all().order_by('-id')
    context = {
        'active_tab': 'approvals',
        'approvals': approvals
    }
    return render(request, 'procurement/approvals.html', context)



@login_required_custom
def purchase_orders_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        po_id = request.POST.get('po_id')
        po = get_object_or_404(PurchaseOrder, id=po_id)
        
        if action == 'track_delivery':
            # Confirmed -> Shipped -> Received -> Invoiced
            stages = ['Confirmed', 'Shipped', 'Received', 'Invoiced']
            try:
                curr_idx = stages.index(po.timeline_status)
                if curr_idx < len(stages) - 1:
                    po.timeline_status = stages[curr_idx + 1]
                    po.save()
                    ActivityLog.objects.create(user=request.user, action='PO Timeline Updated', details=f'PO {po.po_number} advanced to {po.timeline_status}')
            except ValueError:
                po.timeline_status = 'Confirmed'
                po.save()
            return redirect(f'/purchase-orders/?selected_id={po.id}')
        elif action == 'close_po':
            po.status = 'Closed'
            po.timeline_status = 'Invoiced'
            po.save()
            ActivityLog.objects.create(user=request.user, action='PO Closed', details=f'PO {po.po_number} has been closed.')
            return redirect(f'/purchase-orders/?selected_id={po.id}')
        elif action == 'email_po':
            # Console simulation
            recipient = po.quotation.vendor.contact_email
            send_mail(
                f'Purchase Order {po.po_number} from VendorBridge ERP',
                f'Dear {po.quotation.vendor.name},\n\nPlease find attached PO {po.po_number}.',
                'no-reply@vendorbridge.com',
                [recipient],
                fail_silently=False
            )
            ActivityLog.objects.create(user=request.user, action='PO Emailed', details=f'PO {po.po_number} emailed to {recipient}.')
            return redirect(f'/purchase-orders/?selected_id={po.id}')
        elif action == 'generate_invoice':
            # Create Invoice automatically
            if not Invoice.objects.filter(purchase_order=po).exists():
                invoice = Invoice.objects.create(purchase_order=po, status='Posted')
                po.timeline_status = 'Invoiced'
                po.save()
                ActivityLog.objects.create(user=request.user, action='Invoice Generated', details=f'Generated Invoice {invoice.invoice_number} for PO {po.po_number}')
            return redirect('/invoices/')

    pos = PurchaseOrder.objects.all().order_by('-created_at')
    
    # Filter for Vendor
    if request.user.role == 'Vendor':
        my_profile = getattr(request.user, 'vendor_profile', None)
        if my_profile:
            pos = pos.filter(quotation__vendor=my_profile)
        else:
            pos = pos.none()
            
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', 'All')
    if search:
        pos = pos.filter(po_number__icontains=search) | pos.filter(quotation__rfq__title__icontains=search)
    if status_filter != 'All':
        pos = pos.filter(status=status_filter)
        
    selected_id = request.GET.get('selected_id')
    selected_po = None
    if selected_id:
        selected_po = PurchaseOrder.objects.filter(id=selected_id).first()
    if not selected_po and pos.exists():
        selected_po = pos.first()
        
    context = {
        'active_tab': 'purchase_orders',
        'pos': pos,
        'selected_po': selected_po,
        'search': search,
        'status_filter': status_filter
    }
    return render(request, 'procurement/purchase_orders.html', context)

@login_required_custom
def invoices_view(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        invoice_id = request.POST.get('invoice_id')
        invoice = get_object_or_404(Invoice, id=invoice_id)
        
        if action == 'email_invoice':
            recipient = invoice.purchase_order.quotation.vendor.contact_email
            send_mail(
                f'Invoice {invoice.invoice_number} from VendorBridge ERP',
                f'Dear {invoice.purchase_order.quotation.vendor.name},\n\nPlease find attached Invoice {invoice.invoice_number}.',
                'no-reply@vendorbridge.com',
                [recipient],
                fail_silently=False
            )
            ActivityLog.objects.create(user=request.user, action='Invoice Emailed', details=f'Invoice {invoice.invoice_number} emailed to {recipient}.')
            return redirect(f'/invoices/?selected_id={invoice.id}')
        elif action == 'mark_as_paid':
            invoice.status = 'Paid'
            invoice.save()
            ActivityLog.objects.create(user=request.user, action='Invoice Paid', details=f'Invoice {invoice.invoice_number} marked as Paid.')
            return redirect(f'/invoices/?selected_id={invoice.id}')

    invoices = Invoice.objects.all().order_by('-created_at')
    
    # Filter for Vendor
    if request.user.role == 'Vendor':
        my_profile = getattr(request.user, 'vendor_profile', None)
        if my_profile:
            invoices = invoices.filter(purchase_order__quotation__vendor=my_profile)
        else:
            invoices = invoices.none()
            
    search = request.GET.get('search', '')
    status_filter = request.GET.get('status', 'All')
    if search:
        invoices = invoices.filter(invoice_number__icontains=search) | invoices.filter(purchase_order__po_number__icontains=search)
    if status_filter != 'All':
        invoices = invoices.filter(status=status_filter)
        
    selected_id = request.GET.get('selected_id')
    selected_invoice = None
    if selected_id:
        selected_invoice = Invoice.objects.filter(id=selected_id).first()
    if not selected_invoice and invoices.exists():
        selected_invoice = invoices.first()
        
    context = {
        'active_tab': 'invoices',
        'invoices': invoices,
        'selected_invoice': selected_invoice,
        'search': search,
        'status_filter': status_filter
    }
    return render(request, 'procurement/invoices.html', context)

@login_required_custom
def reports_view(request):
    categories = ['IT Hardware', 'Office Supplies', 'Services & Logistics', 'Facilities & Work']
    
    report_data = []
    total_pos_count = 0
    total_target_budget = 0.0
    total_actual_spend = 0.0
    total_savings = 0.0

    for cat in categories:
        pos = PurchaseOrder.objects.filter(quotation__vendor__category=cat)
        pos_count = pos.count()
        
        actual_spend = float(pos.aggregate(Sum('quotation__total_price'))['quotation__total_price__sum'] or 0.0)
        
        target_budget = 0.0
        for po in pos:
            rfq = po.quotation.rfq
            target_budget += sum(float(item.get('qty', 1)) * float(item.get('expected_price', 0)) for item in rfq.items)
        
        savings = max(0.0, target_budget - actual_spend)
        savings_pct = (savings / target_budget * 100.0) if target_budget > 0 else 0.0
        
        report_data.append({
            'category': cat,
            'orders_count': pos_count,
            'target_budget': target_budget,
            'actual_spend': actual_spend,
            'savings': savings,
            'savings_pct': round(savings_pct, 1)
        })
        
        total_pos_count += pos_count
        total_target_budget += target_budget
        total_actual_spend += actual_spend
        total_savings += savings
    
    total_savings_pct = (total_savings / total_target_budget * 100.0) if total_target_budget > 0 else 0.0
    summary_ledger = {
        'orders_count': total_pos_count,
        'target_budget': total_target_budget,
        'actual_spend': total_actual_spend,
        'savings': total_savings,
        'savings_pct': round(total_savings_pct, 1)
    }

    # Chart data
    chart_labels = categories
    chart_data = [item['actual_spend'] for item in report_data]
    
    # Doughnut data: IT Hardware Savings, Office Supplies Savings, Services Savings, Facilities Savings, Committed Spend
    doughnut_data = [
        next(item['savings'] for item in report_data if item['category'] == 'IT Hardware'),
        next(item['savings'] for item in report_data if item['category'] == 'Office Supplies'),
        next(item['savings'] for item in report_data if item['category'] == 'Services & Logistics'),
        next(item['savings'] for item in report_data if item['category'] == 'Facilities & Work'),
        total_actual_spend
    ]

    context = {
        'active_tab': 'reports',
        'report_data': report_data,
        'summary_ledger': summary_ledger,
        'chart_labels_json': json.dumps(chart_labels),
        'chart_data_json': json.dumps(chart_data),
        'doughnut_data_json': json.dumps(doughnut_data),
    }
    return render(request, 'procurement/reports.html', context)

@login_required_custom
def activity_view(request):
    logs = ActivityLog.objects.all().order_by('-timestamp')
    context = {
        'active_tab': 'activity',
        'logs': logs
    }
    return render(request, 'procurement/activity.html', context)

@login_required_custom
def users_view(request):
    if request.user.role != 'Admin':
        return redirect('/')
        
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create_user':
            email = request.POST.get('email')
            password = request.POST.get('password')
            first_name = request.POST.get('first_name')
            last_name = request.POST.get('last_name')
            role = request.POST.get('role')
            
            if not User.objects.filter(email=email).exists():
                User.objects.create_user(
                    email=email, password=password, first_name=first_name, last_name=last_name, role=role
                )
                ActivityLog.objects.create(user=request.user, action='User Created', details=f'Admin created user {email} as {role}')
            return redirect('/users/')
            
    users = User.objects.all()
    context = {
        'active_tab': 'users',
        'users': users
    }
    return render(request, 'procurement/users.html', context)


@login_required_custom
def settings_view(request):
    error = None
    message = None
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_profile':
            email = request.POST.get('email')
            first_name = request.POST.get('first_name')
            last_name = request.POST.get('last_name')
            
            if not email:
                error = "Email address is required."
            else:
                # Check if email is already taken by another user
                if User.objects.filter(email=email).exclude(pk=request.user.pk).exists():
                    error = "This email is already in use by another account."
                else:
                    request.user.email = email
                    request.user.username = email
                    request.user.first_name = first_name
                    request.user.last_name = last_name
                    request.user.save()
                    
                    # Log activity
                    ActivityLog.objects.create(
                        user=request.user, 
                        action='Profile Updated', 
                        details=f'User updated profile: {first_name} {last_name} ({email})'
                    )
                    message = "Profile details successfully updated."
                    
        elif action == 'change_password':
            current_pass = request.POST.get('current_password')
            new_pass = request.POST.get('new_password')
            confirm_pass = request.POST.get('confirm_password')
            
            if not request.user.check_password(current_pass):
                error = "Your current password was incorrect."
            elif new_pass != confirm_pass:
                error = "New password and confirmation do not match."
            elif len(new_pass) < 6:
                error = "Password must be at least 6 characters long."
            else:
                request.user.set_password(new_pass)
                request.user.save()
                
                # Update session to keep user logged in after password change
                from django.contrib.auth import update_session_auth_hash
                update_session_auth_hash(request, request.user)
                
                # Log activity
                ActivityLog.objects.create(
                    user=request.user, 
                    action='Password Changed', 
                    details=f'User successfully changed their password.'
                )
                message = "Password successfully updated."

    context = {
        'active_tab': 'settings',
        'error': error,
        'message': message
    }
    return render(request, 'procurement/settings.html', context)

