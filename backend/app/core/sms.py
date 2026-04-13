"""
Plotra Platform - SMS Service
Handles sending SMS for OTP verification and other notifications
"""
import httpx
from typing import Optional
from urllib.parse import quote
from app.core.config import settings


async def send_sms(
    to_phone: str,
    message: str
) -> bool:
    """
    Send an SMS using Africa's Talking (or similar provider)
    
    Args:
        to_phone: Recipient phone number (with country code, e.g., +254712345678)
        message: SMS message content
        
    Returns:
        True if SMS was sent successfully, False otherwise
    """
    sms_config = settings.sms
    
    # Skip if no API key configured or in debug mode (development mode)
    if not sms_config.api_key or sms_config.debug_mode:
        print(f"[SMS DEV MODE] Would send to {to_phone}: {message}")
        return True
    
    try:
        if sms_config.provider == "africastalking":
            return await send_via_africastalking(to_phone, message)
        else:
            print(f"SMS provider '{sms_config.provider}' not supported")
            return False
            
    except Exception as e:
        print(f"Error sending SMS: {str(e)}")
        if sms_config.debug_mode:
            import traceback
            print(traceback.format_exc())
        return False


async def send_via_africastalking(to_phone: str, message: str) -> bool:
    """Send SMS via Africa's Talking API"""
    sms_config = settings.sms
    
    # Format phone number
    if to_phone.startswith('+'):
        to_phone = to_phone[1:]  # Remove + prefix
    
    # Africa's Talking API endpoint
    # Try the newer v1 API format
    url = "https://api.africastalking.com/version1/messaging"
    
    payload = {
        "username": sms_config.username,
        "to": [to_phone],
        "message": message
    }
    
    # Add sender if provided
    if sms_config.sender_id:
        payload["from"] = sms_config.sender_id
    
    # Convert to form-encoded string (URL encode values)
    form_data = f"username={quote(sms_config.username)}&to={quote(to_phone)}&message={quote(message)}"
    if sms_config.sender_id:
        form_data += f"&from={quote(sms_config.sender_id)}"
    
    headers = {
        "apiKey": sms_config.api_key,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    # For sandbox mode, use the sandbox endpoint
    if sms_config.debug_mode:
        url = "https://api.sandbox.africastalking.com/version1/messaging"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, data=form_data, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                if sms_config.debug_mode:
                    print(f"SMS sent: {result}")
                return True
            else:
                print(f"SMS Error: {response.status_code} - {response.text}")
                return False
                
    except Exception as e:
        print(f"Africa's Talking API error: {str(e)}")
        return False


async def send_otp_sms(to_phone: str, otp: str) -> bool:
    """
    Send OTP via SMS
    
    Args:
        to_phone: Recipient phone number
        otp: 6-digit OTP
        
    Returns:
        True if sent successfully
    """
    message = f"Your Plotra verification code is: {otp}. This code expires in 5 minutes."
    return await send_sms(to_phone, message)