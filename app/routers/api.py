"""
REST API routes for basic operations
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Dict, Any
from pydantic import BaseModel

from ..models import FreeRunnerRequest, EchoRequest
from ..services import ibkr_service, free_runner_service, notification_service
from ..services.stop_loss_service import stop_loss_management_service
from ..utils import format_error_response, format_success_response

router = APIRouter()


def extract_fields_from_malformed_json(raw_text: str) -> dict:
    """
    Extract fields from malformed JSON using regex patterns
    This is a fallback for Discord webhooks with unescaped newlines
    """
    import re
    
    result = {}
    
    # Extract title
    title_match = re.search(r'"title":\s*"([^"]*)"', raw_text)
    if title_match:
        result['title'] = title_match.group(1)
    
    # Extract subtext  
    subtext_match = re.search(r'"subtext":\s*"([^"]*)"', raw_text)
    if subtext_match:
        result['subtext'] = subtext_match.group(1)
    
    # Extract message (more complex due to potential newlines)
    # Look for "message": " and find the closing quote, handling newlines
    message_start = raw_text.find('"message":')
    if message_start != -1:
        # Find the opening quote
        quote_start = raw_text.find('"', message_start + 10)
        if quote_start != -1:
            # Find the closing quote, but skip escaped quotes
            pos = quote_start + 1
            message_content = ""
            while pos < len(raw_text):
                char = raw_text[pos]
                if char == '"':
                    # Check if this quote is escaped
                    if pos > 0 and raw_text[pos-1] != '\\':
                        # This is the closing quote
                        break
                elif char == '\\' and pos + 1 < len(raw_text):
                    # Handle escaped characters
                    next_char = raw_text[pos + 1]
                    if next_char in ['n', 'r', 't', '"', '\\']:
                        message_content += char + next_char
                        pos += 2
                        continue
                message_content += char
                pos += 1
            
            result['message'] = message_content
    
    return result if result else None


# Pydantic models for request validation
class NotificationRequest(BaseModel):
    """Request model for notification endpoint"""
    title: str
    message: str
    subtext: str


@router.post("/notification/debug")
def debug_notification(request: dict):
    """Debug endpoint to see raw request data"""
    return {
        "received_data": request,
        "data_type": str(type(request)),
        "keys": list(request.keys()) if isinstance(request, dict) else "Not a dict"
    }


@router.post("/notification/raw")
async def debug_raw_notification(request: Request):
    """Debug endpoint to see completely raw request data"""
    try:
        # Get raw body
        raw_body = await request.body()
        
        # Try to parse as JSON
        try:
            json_data = await request.json()
        except Exception as e:
            json_data = f"Failed to parse JSON: {e}"
        
        return {
            "raw_body": raw_body.decode('utf-8', errors='ignore'),
            "raw_length": len(raw_body),
            "content_type": request.headers.get("content-type"),
            "json_data": json_data,
            "headers": dict(request.headers)
        }
    except Exception as e:
        return {"error": f"Failed to process request: {e}"}


@router.post("/notification")
async def handle_notification(request: Request):
    """
    Handle incoming notifications with flexible payload parsing
    
    Accepts any JSON payload format and extracts notification data flexibly.
    Primary fields: title, message, subtext
    Fallback fields: not_title, not_ticker, notification (for backward compatibility)
    """
    
    try:
        # Get raw body first
        raw_body = await request.body()
        
        # print("🔍 RAW NOTIFICATION PAYLOAD RECEIVED")
        # print(f"📏 Content Length: {len(raw_body)} bytes")
        # print(f"📄 Content Type: {request.headers.get('content-type', 'Unknown')}")
        # print(f"🌐 Client IP: {request.client.host if request.client else 'Unknown'}")
        # print(f"📦 Raw Body: {raw_body.decode('utf-8', errors='ignore')}")
        # print("-" * 80)
        
        # Try to parse JSON, but be flexible
        payload = None
        try:
            if raw_body:
                import json
                raw_text = raw_body.decode('utf-8')
                
                # Pre-process to handle malformed JSON with unescaped newlines
                # This is a common issue with Discord webhooks that don't properly escape newlines
                try:
                    payload = json.loads(raw_text)
                    # print(f"✅ JSON parsing successful: {type(payload)}")
                except json.JSONDecodeError as e:
                    # print(f"⚠️ Initial JSON parsing failed: {e}")
                    # print("🔧 Attempting to fix malformed JSON with unescaped newlines...")
                    
                    # Simple fix for Discord webhook malformed JSON:
                    # Find the message field and escape newlines within it
                    import re
                    
                    # Look for "message": "content" and escape newlines in the content
                    def fix_message_newlines(text):
                        # Find the start of the message field
                        pattern = r'"message":\s*"([^"]*(?:\n[^"]*)*)"'
                        
                        def escape_newlines(match):
                            content = match.group(1)
                            # Escape newlines and other control characters
                            escaped = content.replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t')
                            return f'"message": "{escaped}"'
                        
                        return re.sub(pattern, escape_newlines, text, flags=re.DOTALL)
                    
                    fixed_json = fix_message_newlines(raw_text)
                    
                    try:
                        payload = json.loads(fixed_json)
                        # print(f"✅ JSON parsing successful after fix: {type(payload)}")
                    except json.JSONDecodeError:
                        # print("❌ JSON fix failed, trying manual extraction...")
                        # Last resort: manually extract fields from malformed JSON
                        payload = extract_fields_from_malformed_json(raw_text)
                        if payload:
                            # print(f"✅ Manual extraction successful: {type(payload)}")
                            pass  # Successfully extracted
                        else:
                            raise ValueError("Could not parse payload")
                    
                # print(f"📋 Parsed payload: {payload}")
            else:
                raise ValueError("Empty request body")
        except Exception as json_error:
            print(f"❌ JSON parsing failed: {json_error}")
            print(f"📦 Treating as raw string: {raw_body.decode('utf-8', errors='ignore')}")
            pass
            
        # print("=" * 80)
        
        # Extract notification fields with flexible parsing
        title = None
        message = None
        subtext = None
        
        if isinstance(payload, dict):
            # Standard JSON object with new field names
            title = payload.get('title', '')
            message = payload.get('message', '')
            subtext = payload.get('subtext', '')
            print(f"🔍 Extracted from dict: title='{title}', message='{message[:100]}...', subtext='{subtext}'")
            
            # Try alternative field names for backward compatibility
            if not title:
                title = payload.get('not_title', payload.get('subject', ''))
            if not message:
                message = payload.get('not_ticker', payload.get('ticker', payload.get('symbol', '')))
            if not subtext:
                subtext = payload.get('notification', payload.get('text', payload.get('body', '')))
                
        elif isinstance(payload, str):
            # String payload - try to extract meaningful info
            subtext = payload
            title = "String Message"
            message = "UNKNOWN"
            
        elif raw_body:
            # Fallback - use raw body as subtext
            subtext = raw_body.decode('utf-8', errors='ignore')
            title = "Raw Message"
            message = "UNKNOWN"
        else:
            raise ValueError("Empty or invalid payload")
        
        # Validate we have at least one meaningful content field
        has_message = message and message.strip()
        has_subtext = subtext and subtext.strip()
        
        if not has_message and not has_subtext:
            raise ValueError("At least one content field is required (message or subtext)")
        
        # Use defaults for missing fields
        if not title or not title.strip():
            title = "Notification"
        if not message or not message.strip():
            message = "GENERAL"
        if not subtext or not subtext.strip():
            subtext = "NO_SUBTEXT"  # Use placeholder instead of empty
            
        # print(f"✅ PARSED FIELDS:")
        # print(f"📋 title: '{title}'")
        # print(f"📊 message: '{message}'")
        # print(f"💬 subtext: '{subtext}'")
        # print("=" * 80)
        
        # Process the notification (using the service's expected field names)
        result = await notification_service.process_notification(
            not_title=title.strip(),
            not_ticker=message.strip(),  # message becomes ticker (contract info)
            notification=subtext.strip() # subtext becomes main notification content
        )
        
        if result["success"]:
            return JSONResponse(
                content=format_success_response(
                    message=result["message"],
                    data=result["data"]
                ),
                status_code=200
            )
        else:
            return JSONResponse(
                content=format_error_response(
                    message=result["message"]
                ),
                status_code=500
            )
            
    except ValueError as ve:
        error_msg = f"Validation error: {str(ve)}"
        # print(f"❌ {error_msg}")
        return JSONResponse(
            content=format_error_response(
                message=error_msg
            ),
            status_code=422
        )
    except Exception as e:
        error_msg = f"Internal server error: {str(e)}"
        # print(f"❌ {error_msg}")
        return JSONResponse(
            content=format_error_response(
                message=error_msg
            ),
            status_code=500
        )


@router.get("/telegram/status")
async def get_telegram_status():
    """Get Telegram bot status and pending messages"""
    try:
        from ..services.telegram_service import telegram_service
        from ..services.telegram_chat_discovery import chat_discovery
        
        pending_messages = telegram_service.get_pending_messages()
        discovered_chats = chat_discovery.get_all_discovered_chats()
        
        return format_success_response(
            message="Telegram status retrieved successfully",
            data={
                "bot_active": True,
                "chat_id": telegram_service.chat_id,
                "pending_messages_count": len(pending_messages),
                "pending_messages": pending_messages,
                "discovered_chats": discovered_chats
            }
        )
    except Exception as e:
        return format_error_response(
            message="Failed to get Telegram status",
            details={"error": str(e)}
        )


@router.post("/telegram/set-chat-id")
async def set_telegram_chat_id(request: Dict[str, Any]):
    """Manually set Telegram chat ID"""
    try:
        chat_id = request.get("chat_id")
        if not chat_id:
            raise ValueError("chat_id is required")
        
        from ..services.telegram_service import telegram_service
        telegram_service.set_chat_id(str(chat_id))
        
        return format_success_response(
            message="Chat ID set successfully",
            data={"chat_id": str(chat_id)}
        )
    except Exception as e:
        return format_error_response(
            message="Failed to set chat ID",
            details={"error": str(e)}
        )


@router.post("/telegram/test-message")
async def send_test_telegram_message():
    """Send a test message to Telegram"""
    try:
        from ..services.telegram_service import telegram_service
        
        result = await telegram_service.send_trading_alert(
            alerter_name="TEST",
            message="This is a test message to verify Telegram integration",
            ticker="TEST",
            additional_info="Test alert from API endpoint"
        )
        
        return format_success_response(
            message="Test message sent" if result["success"] else "Test message failed",
            data=result
        )
    except Exception as e:
        return format_error_response(
            message="Failed to send test message",
            details={"error": str(e)}
        )


@router.get("/alerters")
def get_alerters_info():
    """Get information about supported alerters"""
    try:
        from ..services import alerter_manager, AlerterConfig
        
        alerter_info = alerter_manager.get_supported_alerters()
        
        return format_success_response(
            message="Alerter information retrieved successfully",
            data={
                "supported_alerters": AlerterConfig.get_supported_alerters(),
                "handler_details": alerter_info,
                "total_supported": len(AlerterConfig.get_supported_alerters())
            }
        )
    except Exception as e:
        return format_error_response(
            message="Failed to retrieve alerter information",
            details={"error": str(e)}
        )


@router.get("/health")
def health_check():
    """Health check endpoint"""
    try:
        return format_success_response(
            message="Service is healthy",
            data={"status": "ok", "service": "ibkr-strategy-builder-backend"}
        )
    except Exception as e:
        return format_error_response(
            message="Health check failed",
            details={"error": str(e)}
        )


@router.post("/echo")
def echo(request: EchoRequest):
    """Echo back the request data"""
    try:
        return format_success_response(
            message="Echo successful",
            data={"echo": request.dict()}
        )
    except Exception as e:
        return format_error_response(
            message="Echo failed",
            details={"error": str(e)}
        )


@router.post("/free-runner")
def free_runner(request: FreeRunnerRequest):
    """Execute free runner logic"""
    try:
        result = free_runner_service.execute_free_runner(request.dict())
        
        if result["success"]:
            return format_success_response(
                message=result["message"],
                data=result["data"]
            )
        else:
            return format_error_response(
                message=result["message"],
                details=result.get("details", {})
            )
    except Exception as e:
        return format_error_response(
            message="Free runner execution failed",
            details={"error": str(e)}
        )


@router.post("/test-order-logic")
def test_order_logic(request: Dict[str, Any]):
    """Test order logic without placing actual orders"""
    try:
        result = ibkr_service.test_order_logic(request)
        
        if result["success"]:
            return format_success_response(
                message="Order logic test completed",
                data=result["data"]
            )
        else:
            return format_error_response(
                message="Order logic test failed",
                details=result.get("details", {})
            )
    except Exception as e:
        return format_error_response(
            message="Order logic test execution failed",
            details={"error": str(e)}
        )


@router.post("/stop-loss/start")
def start_stop_loss(request: Dict[str, Any]):
    """Start stop loss monitoring for a position"""
    try:
        result = stop_loss_management_service.start_monitoring(request)
        
        if result["success"]:
            return format_success_response(
                message=result["message"],
                data=result["data"]
            )
        else:
            return format_error_response(
                message=result["message"],
                details=result.get("details", {})
            )
    except Exception as e:
        return format_error_response(
            message="Failed to start stop loss monitoring",
            details={"error": str(e)}
        )


@router.post("/stop-loss/stop")
def stop_stop_loss(request: Dict[str, Any]):
    """Stop stop loss monitoring for a position"""
    try:
        result = stop_loss_management_service.stop_monitoring(request.get("position_id"))
        
        if result["success"]:
            return format_success_response(
                message=result["message"],
                data=result["data"]
            )
        else:
            return format_error_response(
                message=result["message"],
                details=result.get("details", {})
            )
    except Exception as e:
        return format_error_response(
            message="Failed to stop stop loss monitoring",
            details={"error": str(e)}
        )


@router.get("/stop-loss/status")
def stop_loss_status():
    """Get status of all stop loss monitoring"""
    try:
        result = stop_loss_management_service.get_status()
        
        return format_success_response(
            message="Stop loss status retrieved",
            data=result
        )
    except Exception as e:
        return format_error_response(
            message="Failed to get stop loss status",
            details={"error": str(e)}
        )


@router.get("/portfolio/positions")
def get_positions():
    """Get current portfolio positions from IBKR"""
    try:
        result = ibkr_service.get_positions()
        
        if result["success"]:
            return format_success_response(
                message="Positions retrieved successfully",
                data=result["data"]
            )
        else:
            return format_error_response(
                message=result["message"],
                details=result.get("details", {})
            )
    except Exception as e:
        return format_error_response(
            message="Failed to retrieve positions",
            details={"error": str(e)}
        )


@router.get("/portfolio/orders")
def get_orders():
    """Get current orders from IBKR"""
    try:
        result = ibkr_service.get_orders()
        
        if result["success"]:
            return format_success_response(
                message="Orders retrieved successfully",
                data=result["data"]
            )
        else:
            return format_error_response(
                message=result["message"],
                details=result.get("details", {})
            )
    except Exception as e:
        return format_error_response(
            message="Failed to retrieve orders",
            details={"error": str(e)}
        )


@router.get("/contracts/storage")
def get_contract_storage():
    """Get all stored contracts and storage statistics"""
    try:
        from ..services.contract_storage import contract_storage
        
        return format_success_response(
            message="Retrieved contract storage information",
            data={
                "contracts": contract_storage.get_all_contracts(),
                "stats": contract_storage.get_storage_stats()
            }
        )
    except Exception as e:
        return format_error_response(
            message="Failed to retrieve contract storage",
            details={"error": str(e)}
        )


@router.get("/contracts/storage/{alerter_name}")
def get_contract_for_alerter(alerter_name: str):
    """Get the stored contract for a specific alerter"""
    try:
        from ..services.contract_storage import contract_storage
        
        contract = contract_storage.get_contract(alerter_name)
        is_expired = contract_storage.is_contract_expired(alerter_name) if contract else None
        
        return format_success_response(
            message=f"Retrieved contract for {alerter_name}",
            data={
                "alerter_name": alerter_name,
                "contract": contract,
                "is_expired": is_expired,
                "exists": contract is not None
            }
        )
    except Exception as e:
        return format_error_response(
            message=f"Failed to retrieve contract for {alerter_name}",
            details={"error": str(e)}
        )


@router.delete("/contracts/storage/{alerter_name}")
def remove_contract_for_alerter(alerter_name: str):
    """Remove the stored contract for a specific alerter"""
    try:
        from ..services.contract_storage import contract_storage
        
        success = contract_storage.remove_contract(alerter_name)
        
        return format_success_response(
            message=f"Contract removal {'successful' if success else 'failed'} for {alerter_name}",
            data={
                "alerter_name": alerter_name,
                "removed": success
            }
        )
    except Exception as e:
        return format_error_response(
            message=f"Failed to remove contract for {alerter_name}",
            details={"error": str(e)}
        )


@router.post("/contracts/storage/cleanup")
def cleanup_expired_contracts():
    """Clean up all expired contracts"""
    try:
        from ..services.contract_storage import contract_storage
        
        contract_storage.cleanup_expired_contracts()
        
        return format_success_response(
            message="Expired contracts cleanup completed",
            data=contract_storage.get_storage_stats()
        )
    except Exception as e:
        return format_error_response(
            message="Failed to cleanup expired contracts",
            details={"error": str(e)}
        )


@router.get("/stocks/storage")
def get_stock_storage():
    """Get all stored alerted stocks and storage statistics"""
    try:
        from ..services.alerter_stock_storage import alerter_stock_storage
        
        return format_success_response(
            message="Retrieved stock storage information",
            data={
                "stocks": alerter_stock_storage.get_all_stocks(),
                "stats": alerter_stock_storage.get_storage_stats()
            }
        )
    except Exception as e:
        return format_error_response(
            message="Failed to retrieve stock storage",
            details={"error": str(e)}
        )


@router.get("/stocks/storage/{alerter_name}")
def get_stocks_for_alerter(alerter_name: str):
    """Get all stored stocks for a specific alerter"""
    try:
        from ..services.alerter_stock_storage import alerter_stock_storage
        
        all_stocks = alerter_stock_storage.get_alerter_stocks(alerter_name)
        active_stocks = alerter_stock_storage.get_alerter_stocks(alerter_name, status="ACTIVE")
        closed_stocks = alerter_stock_storage.get_alerter_stocks(alerter_name, status="CLOSED")
        
        return format_success_response(
            message=f"Retrieved stocks for {alerter_name}",
            data={
                "alerter_name": alerter_name,
                "all_stocks": all_stocks,
                "active_stocks": active_stocks,
                "closed_stocks": closed_stocks,
                "active_count": len(active_stocks),
                "closed_count": len(closed_stocks),
                "total_count": len(all_stocks)
            }
        )
    except Exception as e:
        return format_error_response(
            message=f"Failed to retrieve stocks for {alerter_name}",
            details={"error": str(e)}
        )


@router.get("/stocks/storage/{alerter_name}/active")
def get_active_stocks_for_alerter(alerter_name: str):
    """Get only active (not closed) stocks for a specific alerter"""
    try:
        from ..services.alerter_stock_storage import alerter_stock_storage
        
        active_stocks = alerter_stock_storage.get_active_stocks(alerter_name)
        
        return format_success_response(
            message=f"Retrieved active stocks for {alerter_name}",
            data={
                "alerter_name": alerter_name,
                "active_tickers": active_stocks,
                "count": len(active_stocks)
            }
        )
    except Exception as e:
        return format_error_response(
            message=f"Failed to retrieve active stocks for {alerter_name}",
            details={"error": str(e)}
        )


@router.post("/stocks/storage/{alerter_name}/{ticker}/close")
def close_stock_alert(alerter_name: str, ticker: str):
    """Close a stock alert (mark as closed, for when user presses Close button in bot)"""
    try:
        from ..services.alerter_stock_storage import alerter_stock_storage
        
        success = alerter_stock_storage.close_stock_alert(alerter_name, ticker)
        
        return format_success_response(
            message=f"Stock alert close {'successful' if success else 'failed'} for {alerter_name}/{ticker}",
            data={
                "alerter_name": alerter_name,
                "ticker": ticker,
                "closed": success
            }
        )
    except Exception as e:
        return format_error_response(
            message=f"Failed to close stock alert for {alerter_name}/{ticker}",
            details={"error": str(e)}
        )


@router.delete("/stocks/storage/{alerter_name}/{ticker}")
def remove_stock_alert(alerter_name: str, ticker: str):
    """Completely remove a stock alert from storage"""
    try:
        from ..services.alerter_stock_storage import alerter_stock_storage
        
        success = alerter_stock_storage.remove_stock_alert(alerter_name, ticker)
        
        return format_success_response(
            message=f"Stock alert removal {'successful' if success else 'failed'} for {alerter_name}/{ticker}",
            data={
                "alerter_name": alerter_name,
                "ticker": ticker,
                "removed": success
            }
        )
    except Exception as e:
        return format_error_response(
            message=f"Failed to remove stock alert for {alerter_name}/{ticker}",
            details={"error": str(e)}
        )
