from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from app.services.penny_stock_monitor import penny_stock_monitor
from app.services.penny_stock_price_monitor import penny_stock_price_monitor

router = APIRouter()


class ChildOrder(BaseModel):
    order_id: str = Field(..., description="Child order id")


class ParentOrderIn(BaseModel):
    parent_order_id: str = Field(..., description="Parent order id")
    # Accept child order id as a plain string (simpler client shape)
    limit_sell: Optional[str] = None
    stop_loss: Optional[str] = None
    # Optional trading hints
    target_price: Optional[float] = Field(None, description="Optional target price for this parent order")
    stop_loss_price: Optional[float] = Field(None, description="Optional stop loss price for this parent order")
    freeRunner: Optional[bool] = Field(False, description="Optional boolean to mark this order as freeRunner; defaults to False")
    minimum_variation: float = Field(0.001, description="Minimum price variation for this order; defaults to 0.001")


class TickerOrdersIn(BaseModel):
    ticker: str = Field(..., description="Stock ticker symbol")
    orders: List[ParentOrderIn]
    minimum_variation: float = Field(0.001, description="Minimum price variation for this ticker; defaults to 0.001")
    entry_price: Optional[float] = Field(None, description="Strategy-level entry price for trailing stop loss")
    freeRunner: Optional[bool] = Field(False, description="Strategy-level free runner flag")
    price_targets: Optional[List[float]] = Field(default_factory=list, description="Strategy-level price targets array")


class BulkOrdersIn(BaseModel):
    orders: List[TickerOrdersIn]


@router.post("/penny-stock/orders", tags=["penny_stock_monitor"])
def add_penny_orders(payload: BulkOrdersIn):
    # Convert to plain dicts for the service
    data = payload.model_dump()
    added = penny_stock_monitor.add_orders(data.get("orders", []))
    return {"success": True, "added_order_ids": added, "added_count": len(added)}


@router.get("/penny-stock/orders", tags=["penny_stock_monitor"])
def list_penny_orders():
    orders = penny_stock_monitor.list_orders()
    return {"orders": orders, "count": len(orders)}


# Price monitoring endpoints
@router.post("/penny-stock/price-monitor/start", tags=["penny_stock_monitor"])
async def start_price_monitor():
    """Start the price monitoring service"""
    try:
        await penny_stock_price_monitor.start()
        return {"success": True, "message": "Price monitoring started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start price monitor: {e}")


@router.post("/penny-stock/price-monitor/stop", tags=["penny_stock_monitor"])
async def stop_price_monitor():
    """Stop the price monitoring service"""
    try:
        await penny_stock_price_monitor.stop()
        return {"success": True, "message": "Price monitoring stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop price monitor: {e}")


@router.get("/penny-stock/price-monitor/status", tags=["penny_stock_monitor"])
def get_price_monitor_status():
    """Get the status of the price monitoring service"""
    return {
        "running": penny_stock_price_monitor._running,
        "poll_interval": penny_stock_price_monitor.poll_interval,
        "trailing_stop_percent": penny_stock_price_monitor.trailing_stop_percent
    }


@router.put("/penny-stock/price-monitor/config", tags=["penny_stock_monitor"])
def update_price_monitor_config(poll_interval: Optional[float] = None, trailing_stop_percent: Optional[float] = None):
    """Update price monitoring configuration"""
    updated = {}
    
    if poll_interval is not None:
        penny_stock_price_monitor.poll_interval = poll_interval
        updated["poll_interval"] = poll_interval
        
    if trailing_stop_percent is not None:
        penny_stock_price_monitor.trailing_stop_percent = trailing_stop_percent
        updated["trailing_stop_percent"] = trailing_stop_percent
    
    return {"success": True, "updated": updated}


# Notification log endpoints
@router.get("/penny-stock/notifications/logs", tags=["penny_stock_monitor"])
def get_notification_logs(limit: Optional[int] = 50):
    """Get penny stock notification logs"""
    import os
    
    try:
        # Get log file path
        logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
        log_file = os.path.join(logs_dir, 'penny_stock_notifications.log')
        
        if not os.path.exists(log_file):
            return {"success": True, "logs": [], "count": 0, "message": "No logs found"}
        
        # Read log file
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Get recent entries (limit)
        recent_lines = lines[-limit:] if len(lines) > limit else lines
        
        # Parse log entries
        parsed_logs = []
        for line in recent_lines:
            try:
                parts = line.strip().split(' | ')
                if len(parts) >= 3:
                    timestamp = parts[0]
                    level = parts[1]
                    content = ' | '.join(parts[2:])
                    
                    # Extract notification type and ticker
                    notification_type = "UNKNOWN"
                    ticker = "Unknown"
                    
                    if content.startswith('[') and ']' in content:
                        end_bracket = content.find(']')
                        notification_type = content[1:end_bracket]
                        remaining = content[end_bracket+1:].strip()
                        if remaining.startswith(' '):
                            parts_after = remaining.split(' | ')
                            if len(parts_after) > 0:
                                ticker = parts_after[0].strip()
                    
                    parsed_logs.append({
                        "timestamp": timestamp,
                        "level": level,
                        "type": notification_type,
                        "ticker": ticker,
                        "content": content,
                        "raw": line.strip()
                    })
            except Exception:
                # Include malformed entries as raw
                parsed_logs.append({
                    "timestamp": "Unknown",
                    "level": "ERROR",
                    "type": "MALFORMED",
                    "ticker": "Unknown",
                    "content": line.strip(),
                    "raw": line.strip()
                })
        
        return {
            "success": True,
            "logs": parsed_logs,
            "count": len(parsed_logs),
            "total_in_file": len(lines),
            "log_file": log_file
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read notification logs: {e}")


@router.delete("/penny-stock/notifications/logs", tags=["penny_stock_monitor"])
def clear_notification_logs():
    """Clear all penny stock notification logs"""
    import os
    
    try:
        # Get log file path
        logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
        log_file = os.path.join(logs_dir, 'penny_stock_notifications.log')
        
        if os.path.exists(log_file):
            # Clear the file
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write("")
            return {"success": True, "message": "Notification logs cleared"}
        else:
            return {"success": True, "message": "No log file to clear"}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear notification logs: {e}")
