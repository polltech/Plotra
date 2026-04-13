"""
Plotra Platform - SMS Service
Handles sending SMS for OTP verification and other notifications.
Defaults to dev/debug mode (console print) when no SMS provider is configured.
"""
import os
import httpx
from urllib.parse import quote


# Read SMS config from environment variables (no entry in settings yet)
_SMS_API_KEY = os.environ.get("AFRICASTALKING_API_KEY", "")
_SMS_USERNAME = os.environ.get("AFRICASTALKING_USERNAME", "sandbox")
_SMS_SENDER_ID = os.environ.get("AFRICASTALKING_SENDER_ID", "")
_SMS_DEBUG = os.environ.get("SMS_DEBUG_MODE", "true").lower() in ("1", "true", "yes")


async def send_sms(to_phone: str, message: str) -> bool:
    """
    Send an SMS. Falls back to console output when no API key is configured.

    Args:
        to_phone: Recipient phone number with country code (e.g., +254712345678)
        message: SMS message text

    Returns:
        True if sent (or printed in dev mode) successfully, False on error
    """
    if not _SMS_API_KEY or _SMS_DEBUG:
        print(f"[SMS DEV MODE] To: {to_phone} | Message: {message}")
        return True

    return await _send_via_africastalking(to_phone, message)


async def _send_via_africastalking(to_phone: str, message: str) -> bool:
    """Send SMS via Africa's Talking API."""
    # Remove leading + for the API
    phone = to_phone.lstrip('+')

    url = (
        "https://api.sandbox.africastalking.com/version1/messaging"
        if _SMS_DEBUG
        else "https://api.africastalking.com/version1/messaging"
    )

    form_data = f"username={quote(_SMS_USERNAME)}&to={quote(phone)}&message={quote(message)}"
    if _SMS_SENDER_ID:
        form_data += f"&from={quote(_SMS_SENDER_ID)}"

    headers = {
        "apiKey": _SMS_API_KEY,
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, data=form_data, headers=headers)
            if response.status_code == 200:
                return True
            print(f"SMS Error: {response.status_code} - {response.text}")
            return False
    except Exception as exc:
        print(f"Africa's Talking API error: {exc}")
        return False


async def send_otp_sms(to_phone: str, otp: str) -> bool:
    """Send an OTP code via SMS."""
    message = f"Your Plotra verification code is: {otp}. This code expires in 5 minutes."
    return await send_sms(to_phone, message)
