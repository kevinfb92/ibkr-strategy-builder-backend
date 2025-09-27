"""
REST API routes for basic operations
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from typin        print(f"✅ PARSED FIELDS:")
        print(f"📋 title: '{title}'")
        print(f"📊 message: '{message}'")
        print(f"💬 subtext: '{subtext}'")
        print("=" * 80)
        
        # Process the notification
        result = notification_service.process_notification(
            not_title=title.strip(),
            not_ticker=message.strip().upper(),
            notification=subtext.strip()
        )t, Any
from pydantic import BaseModel

from ..models import FreeRunnerRequest, EchoRequest
from ..services import ibkr_service, free_runner_service, notification_service
from ..services.stop_loss_service import stop_loss_management_service
from ..utils import format_error_response, format_success_response

router = APIRouter()


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
            import json
            json_body = json.loads(raw_body.decode('utf-8'))
        except:
            json_body = "Could not parse as JSON"
        
        print("=" * 80)
        print("🔍 COMPLETELY RAW REQUEST DEBUG")
        print("=" * 80)
        print(f"📦 Raw body bytes: {raw_body}")
        print(f"📦 Raw body string: {raw_body.decode('utf-8', errors='ignore')}")
        print(f"📦 Parsed JSON: {json_body}")
        print(f"📦 Headers: {dict(request.headers)}")
        print(f"📦 Content-Type: {request.headers.get('content-type')}")
        print("=" * 80)
        
        return {
            "raw_body_bytes": str(raw_body),
            "raw_body_string": raw_body.decode('utf-8', errors='ignore'),
            "parsed_json": json_body,
            "headers": dict(request.headers),
            "content_type": request.headers.get('content-type')
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/health")
def health():
    """Health check endpoint"""
    return {"status": "ok"}


@router.post("/echo")
def echo(request: EchoRequest):
    """Echo endpoint for testing"""
    return JSONResponse(content={"echo": request.data})


@router.post("/notification")
async def handle_notification(request: Request):
    """
    Handle incoming notifications with flexible payload parsing
    
    Accepts any type of payload and attempts to parse the required fields.
    Processes and stores them for further handling.
    """
    try:
        # Get raw body
        raw_body = await request.body()
        
        # Print the exact payload received
        print("=" * 80)
        print("🔍 RAW NOTIFICATION PAYLOAD RECEIVED")
        print("=" * 80)
        print(f"📦 Raw body bytes: {raw_body}")
        print(f"📦 Raw body string: {raw_body.decode('utf-8', errors='ignore')}")
        print(f"📦 Content-Type: {request.headers.get('content-type')}")
        print(f"📦 Headers: {dict(request.headers)}")
        
        # Try to parse the payload
        payload = None
        try:
            import json
            payload = json.loads(raw_body.decode('utf-8'))
            print(f"📦 Parsed JSON: {payload}")
        except Exception as json_error:
            print(f"❌ JSON parsing failed: {json_error}")
            print(f"📦 Treating as raw string: {raw_body.decode('utf-8', errors='ignore')}")
            
        print("=" * 80)
        
        # Extract notification fields with flexible parsing
        title = None
        message = None
        subtext = None
        
        if isinstance(payload, dict):
            # Standard JSON object
            title = payload.get('title', '')
            message = payload.get('message', '')
            subtext = payload.get('subtext', '')
            
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
        
        # Validate we have the minimum required data
        if not subtext or not subtext.strip():
            raise ValueError("Subtext message is required (missing 'subtext', 'notification', 'text', or 'body' field)")
            
        # Use defaults for missing optional fields
        if not title or not title.strip():
            title = "Notification"
        if not message or not message.strip():
            message = "GENERAL"
            
        print(f"✅ PARSED FIELDS:")
        print(f"📋 not_title: '{not_title}'")
        print(f"� not_ticker: '{not_ticker}'")
        print(f"💬 notification: '{notification}'")
        print("=" * 80)
        
        # Process the notification
        result = notification_service.process_notification(
            not_title=not_title.strip(),
            not_ticker=not_ticker.strip().upper(),
            notification=notification.strip()
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
                content=format_error_response(result["message"]),
                status_code=400
            )
            
    except Exception as e:
        error_msg = f"Error processing notification: {str(e)}"
        print(f"❌ {error_msg}")
        return JSONResponse(
            content=format_error_response(error_msg),
            status_code=500
        )


@router.get("/positions")
def get_positions():
    """Get current positions to know which contracts to subscribe to for P&L"""
    try:
        positions = ibkr_service.get_formatted_positions()
        return JSONResponse(content={"positions": positions})
    except Exception as e:
        return JSONResponse(
            content=format_error_response(str(e)), 
            status_code=500
        )


@router.post("/free-runner")
def create_free_runner(request: FreeRunnerRequest):
    """Create a free runner tracking order for a stock position"""
    try:
        result = free_runner_service.create_free_runner(request.conid, request.price)
        return JSONResponse(content=format_success_response(
            data=result,
            message=f"Free runner created for {result.get('symbol')}"
        ))
        
    except ValueError as e:
        return JSONResponse(
            content=format_error_response(str(e)), 
            status_code=404
        )
    except Exception as e:
        return JSONResponse(
            content=format_error_response(str(e)), 
            status_code=500
        )


@router.post("/test-order-logic")
def test_order_logic(request: Dict[str, Any]):
    """Test the order placement logic without actually placing orders"""
    try:
        conid = request.get("conid")
        target_price = request.get("target_price", 0)
        
        if not conid:
            return JSONResponse(
                content=format_error_response("Missing conid"), 
                status_code=400
            )
        
        # Find the position to test logic
        position = ibkr_service.find_position_by_conid(conid)
        if not position:
            return JSONResponse(
                content=format_error_response(f"No position found for conid {conid}"), 
                status_code=404
            )
        
        # Calculate what the trailing stop would be
        entry_price = position.get("avgPrice", 0)
        position_size = position.get("position", 0)
        is_long = position_size > 0
        
        if is_long and target_price > entry_price:
            price_gain = target_price - entry_price
            trailing_amount = price_gain * 0.10
            stop_price = target_price - trailing_amount
            gain_preserved_pct = ((stop_price - entry_price) / (target_price - entry_price)) * 100
        else:
            price_gain = trailing_amount = stop_price = gain_preserved_pct = None
        
        return JSONResponse(content=format_success_response(
            data={
                "position": {
                    "conid": conid,
                    "symbol": position.get("contractDesc"),
                    "size": position_size,
                    "entry_price": entry_price,
                    "is_long": is_long
                },
                "trailing_stop_calculation": {
                    "target_price": target_price,
                    "entry_price": entry_price,
                    "price_gain": price_gain,
                    "trailing_amount": trailing_amount,
                    "stop_price": stop_price,
                    "gain_preserved_pct": gain_preserved_pct
                } if is_long and target_price > entry_price else None,
                "order_would_be_placed": is_long and target_price > entry_price,
                "confirmation_handling": "Ready - will handle up to 5 confirmation rounds"
            },
            message="Order logic test completed"
        ))
        
    except Exception as e:
        return JSONResponse(
            content=format_error_response(str(e)), 
            status_code=500
        )


@router.post("/test-place-trailing-limit-order")
def test_place_trailing_limit_order(request: Dict[str, Any]):
    """Test placing a trailing limit order directly with extended hours support"""
    try:
        conid = request.get("conid")
        quantity = request.get("quantity", 0)
        trailing_amount = request.get("trailing_amount", 0)
        limit_offset = request.get("limit_offset", 0.01)  # Default 1 cent limit offset
        
        if not all([conid, quantity, trailing_amount]):
            return JSONResponse(
                content=format_error_response("Missing required fields: conid, quantity, trailing_amount"), 
                status_code=400
            )
        
        # Validate the position exists
        position = ibkr_service.find_position_by_conid(conid)
        if not position:
            return JSONResponse(
                content=format_error_response(f"No position found for conid {conid}"), 
                status_code=404
            )
        
        # Attempt to place the trailing limit order
        try:
            order_result = ibkr_service.place_trailing_limit_order(
                conid=conid,
                quantity=quantity,
                trailing_amount=trailing_amount,
                limit_offset=limit_offset
            )
            
            return JSONResponse(content=format_success_response(
                data={
                    "order_result": order_result,
                    "order_type": "TRAILLMT",
                    "extended_hours": True,
                    "parameters": {
                        "conid": conid,
                        "quantity": quantity,
                        "trailing_amount": trailing_amount,
                        "limit_offset": limit_offset
                    }
                },
                message="Trailing limit order placed successfully"
            ))
            
        except Exception as order_error:
            return JSONResponse(
                content=format_error_response(f"Failed to place trailing limit order: {str(order_error)}"), 
                status_code=500
            )
        
    except Exception as e:
        return JSONResponse(
            content=format_error_response(str(e)), 
            status_code=500
        )


@router.post("/test-place-order")
def test_place_order(request: Dict[str, Any]):
    """Test placing a trailing stop order directly (independent of free runner logic)"""
    try:
        conid = request.get("conid")
        quantity = request.get("quantity", 0)
        trailing_amount = request.get("trailing_amount", 0)
        
        if not all([conid, quantity, trailing_amount]):
            return JSONResponse(
                content=format_error_response("Missing required fields: conid, quantity, trailing_amount"), 
                status_code=400
            )
        
        # Validate the position exists
        position = ibkr_service.find_position_by_conid(conid)
        if not position:
            return JSONResponse(
                content=format_error_response(f"No position found for conid {conid}"), 
                status_code=404
            )
        
        # Attempt to place the trailing stop order
        try:
            order_result = ibkr_service.place_trailing_stop_order(
                conid=conid,
                quantity=abs(float(quantity)),
                trailing_amount=float(trailing_amount)
            )
            
            return JSONResponse(content=format_success_response(
                data={
                    "position": {
                        "conid": conid,
                        "symbol": position.get("contractDesc"),
                        "current_position": position.get("position"),
                        "avg_price": position.get("avgPrice"),
                        "current_price": position.get("mktPrice")
                    },
                    "order_request": {
                        "quantity": abs(float(quantity)),
                        "trailing_amount": float(trailing_amount),
                        "order_type": "TRAIL",
                        "side": "SELL"
                    },
                    "order_result": order_result,
                    "confirmations_handled": order_result.get("confirmations_processed", 0) if isinstance(order_result, dict) else 0
                },
                message="Trailing stop order placement test completed"
            ))
            
        except Exception as order_error:
            return JSONResponse(content=format_error_response(
                f"Order placement failed: {str(order_error)}"
            ), status_code=500)
        
    except Exception as e:
        return JSONResponse(
            content=format_error_response(str(e)), 
            status_code=500
        )


@router.post("/stop-loss-management")
def create_stop_loss_management(request: Dict[str, Any]):
    """
    Create stop loss management for a position
    
    Monitors position PnL and adjusts stop-limit orders to break-even when threshold is reached
    
    Payload:
    {
        "conid": 725797159,
        "percentage": 5.0  // PnL percentage threshold (e.g., 5.0 for 5%)
    }
    """
    try:
        conid = request.get("conid")
        percentage = request.get("percentage")
        
        if not conid:
            return JSONResponse(
                content=format_error_response("Missing required field: conid"), 
                status_code=400
            )
        
        if percentage is None:
            return JSONResponse(
                content=format_error_response("Missing required field: percentage"), 
                status_code=400
            )
        
        try:
            conid = int(conid)
            percentage = float(percentage)
        except (ValueError, TypeError):
            return JSONResponse(
                content=format_error_response("Invalid data types: conid must be int, percentage must be float"), 
                status_code=400
            )
        
        if percentage <= 0:
            return JSONResponse(
                content=format_error_response("Percentage must be positive"), 
                status_code=400
            )
        
        # Create stop loss management
        result = stop_loss_management_service.create_stop_loss_management(conid, percentage)
        
        if result.get("success"):
            return JSONResponse(content=format_success_response(
                data=result,
                message=result.get("message", "Stop loss management created successfully")
            ))
        else:
            return JSONResponse(
                content=format_error_response(result.get("error", "Failed to create stop loss management")), 
                status_code=400
            )
        
    except Exception as e:
        return JSONResponse(
            content=format_error_response(str(e)), 
            status_code=500
        )


@router.get("/stop-loss-management")
def get_stop_loss_configurations():
    """Get all active stop loss management configurations"""
    try:
        configurations = stop_loss_management_service.get_active_configurations()
        return JSONResponse(content=format_success_response(
            data=configurations,
            message="Stop loss configurations retrieved successfully"
        ))
        
    except Exception as e:
        return JSONResponse(
            content=format_error_response(str(e)), 
            status_code=500
        )


@router.delete("/stop-loss-management/{conid}")
def remove_stop_loss_management(conid: int):
    """Remove stop loss management for a specific position"""
    try:
        result = stop_loss_management_service.remove_configuration(conid)
        
        if result.get("success"):
            return JSONResponse(content=format_success_response(
                data=result,
                message=result.get("message", "Stop loss management removed successfully")
            ))
        else:
            return JSONResponse(
                content=format_error_response(result.get("error", "Failed to remove stop loss management")), 
                status_code=404
            )
        
    except Exception as e:
        return JSONResponse(
            content=format_error_response(str(e)), 
            status_code=500
        )


# Additional notification management endpoints
@router.get("/notifications")
def get_notifications(limit: int = None):
    """Get stored notifications (newest first)"""
    try:
        notifications = notification_service.get_notifications(limit=limit)
        return JSONResponse(content=format_success_response(
            data={
                "notifications": notifications,
                "total_count": notification_service.get_notification_count()
            },
            message=f"Retrieved {len(notifications)} notifications"
        ))
    except Exception as e:
        return JSONResponse(
            content=format_error_response(str(e)),
            status_code=500
        )


@router.delete("/notifications")
def clear_notifications():
    """Clear all stored notifications"""
    try:
        result = notification_service.clear_notifications()
        return JSONResponse(content=format_success_response(
            data=result,
            message=result["message"]
        ))
    except Exception as e:
        return JSONResponse(
            content=format_error_response(str(e)),
            status_code=500
        )
