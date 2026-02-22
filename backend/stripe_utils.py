"""
ResumeRadar -- Stripe Checkout Utilities
Handles payment session creation and verification for the CV Builder.
"""

import os
import stripe


# Initialize Stripe with secret key
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


def create_checkout_session(cv_token, template, success_url, cancel_url, delivery_email=None):
    """
    Create a Stripe Checkout session for a £2 CV download.

    Args:
        cv_token: UUID token identifying the generated CV in Redis
        template: chosen PDF template name (classic/modern/minimal)
        success_url: URL to redirect after successful payment
        cancel_url: URL to redirect if user cancels
        delivery_email: optional email to send PDF copy to (stored in metadata)

    Returns:
        dict with session_id and checkout_url, or error
    """
    price_id = os.getenv("STRIPE_PRICE_ID")
    if not price_id:
        return {"error": "Payment service not configured."}

    try:
        metadata = {
            "cv_token": cv_token,
            "template": template,
        }
        if delivery_email:
            metadata["delivery_email"] = delivery_email

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price": price_id,
                "quantity": 1,
            }],
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata,
        )
        return {
            "session_id": session.id,
            "checkout_url": session.url,
        }
    except stripe.error.StripeError as e:
        print(f"Stripe checkout error: {str(e)}")
        return {"error": "Could not create payment session. Please try again."}


def verify_checkout_payment(session_id, expected_token):
    """
    Verify that a Stripe Checkout session was paid and matches the expected CV token.

    Args:
        session_id: Stripe Checkout session ID
        expected_token: the CV token we expect in the session metadata

    Returns:
        dict with verified=True/False and template choice
    """
    try:
        session = stripe.checkout.Session.retrieve(session_id)

        if session.payment_status != "paid":
            return {"verified": False, "reason": "Payment not completed."}

        token_in_metadata = session.metadata.get("cv_token", "")
        if token_in_metadata != expected_token:
            return {"verified": False, "reason": "Token mismatch."}

        return {
            "verified": True,
            "template": session.metadata.get("template", "classic"),
            "delivery_email": session.metadata.get("delivery_email", ""),
        }
    except stripe.error.StripeError as e:
        print(f"Stripe verify error: {str(e)}")
        return {"verified": False, "reason": "Could not verify payment."}


def verify_webhook_signature(payload, sig_header):
    """
    Validate a Stripe webhook signature.

    Args:
        payload: raw request body bytes
        sig_header: Stripe-Signature header value

    Returns:
        Stripe Event object if valid, None if invalid
    """
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        print("Stripe webhook secret not configured")
        return None

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
        return event
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        print(f"Stripe webhook verification failed: {str(e)}")
        return None
