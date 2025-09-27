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
        
        print("🔍 RAW NOTIFICATION PAYLOAD RECEIVED")
        print(f"📏 Content Length: {len(raw_body)} bytes")
        print(f"📄 Content Type: {request.headers.get('content-type', 'Unknown')}")
        print(f"🌐 Client IP: {request.client.host if request.client else 'Unknown'}")
        print(f"📦 Raw Body: {raw_body.decode('utf-8', errors='ignore')}")
        print("-" * 80)
        
        # Try to parse JSON, but be flexible
        payload = None
        try:
            if raw_body:
                import json
                payload = json.loads(raw_body.decode('utf-8'))
                print(f"✅ JSON parsing successful: {type(payload)}")
                print(f"📋 Parsed payload: {payload}")
            else:
                raise ValueError("Empty request body")
        except Exception as json_error:
            print(f"❌ JSON parsing failed: {json_error}")
            print(f"📦 Treating as raw string: {raw_body.decode('utf-8', errors='ignore')}")
            
        print("=" * 80)
        
        # Extract notification fields with flexible parsing
        title = None
        message = None
        subtext = None
        
        if isinstance(payload, dict):
            # Standard JSON object with new field names
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
        print(f"📋 title: '{title}'")
        print(f"📊 message: '{message}'")
        print(f"💬 subtext: '{subtext}'")
        print("=" * 80)
        
        # Process the notification (using the service's expected field names)
        result = notification_service.process_notification(
            not_title=title.strip(),
            not_ticker=message.strip().upper(),
            notification=subtext.strip()
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
                    message=result["message"],
                    details=result.get("details", {})
                ),
                status_code=500
            )
            
    except ValueError as ve:
        error_msg = f"Validation error: {str(ve)}"
        print(f"❌ {error_msg}")
        return JSONResponse(
            content=format_error_response(
                message=error_msg,
                details={"error_type": "validation_error"}
            ),
            status_code=422
        )
    except Exception as e:
        error_msg = f"Internal server error: {str(e)}"
        print(f"❌ {error_msg}")
        return JSONResponse(
            content=format_error_response(
                message=error_msg,
                details={"error_type": "internal_error"}
            ),
            status_code=500
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
