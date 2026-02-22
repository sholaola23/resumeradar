"""
Paystack payment integration for ResumeRadar CV Builder.
Handles transaction initialization, verification, and webhook validation.
Nigerian users pay in Naira via bank transfer, USSD, or cards.

Paystack is offered as an explicit opt-in for users in Nigeria.
Stripe remains the default payment gateway for all other regions.
"""
import os
import hmac
import hashlib
import requests

PAYSTACK_API_BASE = "https://api.paystack.co"

# NGN price in kobo (100 kobo = 1 NGN). Env-configurable so it can be
# adjusted for FX drift without a code deploy.
PAYSTACK_AMOUNT_KOBO = int(os.getenv("PAYSTACK_AMOUNT_KOBO", "350000"))  # 350000 kobo = NGN 3,500
PAYSTACK_CURRENCY = "NGN"


def create_paystack_transaction(cv_token, template, callback_url, customer_email, format_choice="both"):
    """
    Initialize a Paystack transaction. Equivalent to Stripe's create_checkout_session().

    Args:
        cv_token: UUID token identifying the generated CV in Redis
        template: chosen PDF template name (classic/modern/minimal)
        callback_url: URL to redirect after payment (with token embedded)
        customer_email: REQUIRED - real customer email for receipts + risk scoring
        format_choice: download format ("pdf", "docx", or "both")

    Returns:
        dict with authorization_url and reference, or error
    """
    secret_key = os.getenv("PAYSTACK_SECRET_KEY")
    if not secret_key:
        return {"error": "Paystack not configured."}

    if not customer_email:
        return {"error": "Email is required for Naira payments."}

    metadata = {
        "cv_token": cv_token,
        "template": template,
        "delivery_email": customer_email,
        "format": format_choice,
        "custom_fields": [
            {"display_name": "Product", "variable_name": "product", "value": "ResumeRadar CV Download"}
        ],
    }

    try:
        response = requests.post(
            f"{PAYSTACK_API_BASE}/transaction/initialize",
            json={
                "email": customer_email,
                "amount": PAYSTACK_AMOUNT_KOBO,
                "currency": PAYSTACK_CURRENCY,
                "reference": f"rr_cv_{cv_token[:12]}_{os.urandom(4).hex()}",
                "callback_url": callback_url,
                "channels": ["card", "bank_transfer", "ussd", "mobile_money", "qr"],
                "metadata": metadata,
            },
            headers={
                "Authorization": f"Bearer {secret_key}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        result = response.json()

        if not result.get("status"):
            return {"error": result.get("message", "Paystack initialization failed.")}

        return {
            "authorization_url": result["data"]["authorization_url"],
            "reference": result["data"]["reference"],
        }
    except requests.RequestException as e:
        print(f"Paystack init error: {e}")
        return {"error": "Could not create payment session. Please try again."}


def verify_paystack_payment(reference, expected_token):
    """
    Verify a Paystack transaction by reference. Equivalent to Stripe's verify_checkout_payment().

    Security: checks data.status, amount, currency, AND token metadata.
    - Amount must match PAYSTACK_AMOUNT_KOBO (prevents tampered transactions)
    - Currency must be NGN
    - Token in metadata must match the expected CV token

    Args:
        reference: Paystack transaction reference from callback URL
        expected_token: the CV token we expect in metadata

    Returns:
        dict with verified=True/False and template choice
    """
    secret_key = os.getenv("PAYSTACK_SECRET_KEY")
    if not secret_key:
        return {"verified": False, "reason": "Paystack not configured."}

    try:
        response = requests.get(
            f"{PAYSTACK_API_BASE}/transaction/verify/{reference}",
            headers={"Authorization": f"Bearer {secret_key}"},
            timeout=15,
        )
        result = response.json()

        if not result.get("status") or not result.get("data"):
            return {"verified": False, "reason": "Verification failed."}

        data = result["data"]

        # CRITICAL: check data.status, NOT top-level status
        if data.get("status") != "success":
            return {"verified": False, "reason": "Payment not completed."}

        # Verify amount matches expected price (prevents tampered transactions)
        if data.get("amount") != PAYSTACK_AMOUNT_KOBO:
            print(f"Paystack amount mismatch: expected {PAYSTACK_AMOUNT_KOBO}, got {data.get('amount')}")
            return {"verified": False, "reason": "Payment amount mismatch."}

        # Verify currency matches
        if data.get("currency") != PAYSTACK_CURRENCY:
            print(f"Paystack currency mismatch: expected {PAYSTACK_CURRENCY}, got {data.get('currency')}")
            return {"verified": False, "reason": "Payment currency mismatch."}

        # Verify token in metadata
        metadata = data.get("metadata", {})
        token_in_metadata = metadata.get("cv_token", "")
        if token_in_metadata != expected_token:
            return {"verified": False, "reason": "Token mismatch."}

        return {
            "verified": True,
            "template": metadata.get("template", "classic"),
            "delivery_email": metadata.get("delivery_email", ""),
            "format": metadata.get("format", ""),
        }
    except requests.RequestException as e:
        print(f"Paystack verify error: {e}")
        return {"verified": False, "reason": "Could not verify payment."}


def verify_paystack_webhook(payload_bytes, signature):
    """
    Validate a Paystack webhook signature using HMAC SHA512.
    Unlike Stripe, Paystack uses the same secret key (not a separate webhook secret).

    Args:
        payload_bytes: raw request body bytes
        signature: X-Paystack-Signature header value

    Returns:
        True if valid, False if invalid
    """
    secret_key = os.getenv("PAYSTACK_SECRET_KEY")
    if not secret_key:
        return False

    computed = hmac.new(
        secret_key.encode("utf-8"),
        payload_bytes,
        hashlib.sha512,
    ).hexdigest()

    return hmac.compare_digest(computed, signature)


def format_naira_price():
    """Return the current Naira price as a formatted string for display."""
    naira = PAYSTACK_AMOUNT_KOBO // 100
    return f"\u20a6{naira:,}"
