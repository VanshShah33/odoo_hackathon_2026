import time
import random
import threading
from django.utils import timezone
from .models import RFQ, Quotation, VendorProfile, Notification, ActivityLog, User

def simulate_vendor_responses(rfq_id):
    """
    Run in a background thread. Waits a few seconds, then generates quotations
    from all assigned vendors for the given RFQ.
    """
    # Wait for 5 seconds to simulate real-time bidding latency
    time.sleep(5)
    
    try:
        rfq = RFQ.objects.get(id=rfq_id)
        if rfq.status != 'Sent':
            return
            
        vendors = rfq.assigned_vendors.all()
        if not vendors:
            return

        print(f"[Simulator] Generating bids for RFQ: {rfq.rfq_number}")

        # Fetch an admin or system user for logging
        system_user = User.objects.filter(role='Admin').first()
        if not system_user:
            system_user = User.objects.first()

        for vendor in vendors:
            # Check if quotation already exists
            if Quotation.objects.filter(rfq=rfq, vendor=vendor).exists():
                continue

            # Generate item quotation details
            items_quotation = []
            for item in rfq.items:
                qty = float(item.get('qty', 1))
                # Add random deviation of -15% to +10% to expected price
                # If expected price is not present, use a default base
                expected_price = float(item.get('expected_price', 100))
                factor = random.uniform(0.85, 1.10)
                unit_price = round(expected_price * factor, 2)
                
                items_quotation.append({
                    'name': item.get('name', 'Product'),
                    'spec': item.get('spec', ''),
                    'qty': qty,
                    'unit_price': unit_price
                })

            # Create quotation
            quote = Quotation(
                rfq=rfq,
                vendor=vendor,
                delivery_timeline_days=random.randint(3, 12),
                items_quotation=items_quotation,
                notes=f"We are pleased to submit our competitive offer for {rfq.title}. Looking forward to working together.",
                status='Submitted'
            )
            quote.save()

            # Create notification for Procurement Officer
            Notification.objects.create(
                user=rfq.created_by,
                title="Quotation Received",
                message=f"Vendor '{vendor.name}' has submitted a quotation for {rfq.rfq_number} ({rfq.title})."
            )

            # Log activity
            ActivityLog.objects.create(
                user=vendor.user,
                action="Quotation Submitted",
                details=f"Vendor '{vendor.name}' submitted quote for {rfq.rfq_number}. Total: ₹{quote.total_price:.2f}"
            )

        # Update RFQ status
        rfq.status = 'Received'
        rfq.save()

        # Notify Procurement Officer that RFQ is updated
        Notification.objects.create(
            user=rfq.created_by,
            title="RFQ Updated",
            message=f"All assigned vendors have submitted quotations for {rfq.rfq_number}. You can now compare quotes."
        )

        ActivityLog.objects.create(
            user=system_user,
            action="RFQ Bidding Completed",
            details=f"Received responses from all vendors for {rfq.rfq_number}."
        )

        print(f"[Simulator] Bidding completed for RFQ: {rfq.rfq_number}")

    except Exception as e:
        print(f"[Simulator ERROR] Failed simulating bids for RFQ {rfq_id}: {str(e)}")

def trigger_simulation(rfq_id):
    thread = threading.Thread(target=simulate_vendor_responses, args=(rfq_id,))
    thread.daemon = True
    thread.start()
