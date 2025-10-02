from fastapi import APIRouter, HTTPException, Query
from typing import Any, Dict, List
import asyncio

from ..services import penny_stock_watcher, penny_stock_monitor
from ..services.ibkr_service import IBKRService, ibkr_service
from ..services.order_tracking_service import order_tracking_service
from ..services.handlers.lite_handlers import _cleanup_stale_alerts, _clear_all_alerts

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/penny-watcher")
def penny_watcher_status(limit: int = Query(10, ge=1, le=100), offset: int = Query(0, ge=0)) -> Dict[str, Any]:
    """Return watcher status and a paginated summary of stored penny orders.

    Query params:
    - limit: number of orders to return in the sample (default 10, max 100)
    - offset: offset into the stored orders list
    """
    try:
        watcher = penny_stock_watcher.penny_stock_watcher
        status = watcher.get_status() if hasattr(watcher, 'get_status') else {
            'running': bool(getattr(watcher, '_running', False)),
            'last_polled_at': getattr(watcher, 'last_polled_at', None),
            'subscribed': bool(getattr(watcher, 'subscribed', False)),
        }

        orders = penny_stock_monitor.penny_stock_monitor.list_orders()

        # counts by status
        counts: Dict[str, int] = {}
        for o in orders:
            st = (o.get('status') or 'UNKNOWN')
            counts[st] = counts.get(st, 0) + 1

        # build compact sample
        sample: List[Dict[str, Any]] = []
        for o in orders[offset:offset+limit]:
            sample.append({
                'parent_order_id': o.get('parent_order_id') or o.get('parent') or None,
                'ticker': o.get('ticker'),
                'status': o.get('status'),
                'created_at': o.get('created_at'),
                'last_update_at': (o.get('last_update') or {}).get('updated_at')
            })

        return {
            'watcher_running': bool(status.get('running')),
            'watcher_last_polled_at': status.get('last_polled_at'),
            'watcher_subscribed': bool(status.get('subscribed')),
            'tracked_count': len(orders),
            'counts_by_status': counts,
            'orders_sample': sample,
            'limit': limit,
            'offset': offset,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/penny-watcher/simulate")
def penny_watcher_simulate(payload: Dict[str, Any]):
    """Simulate receiving an order-update message to exercise the watcher.

    Example payload:
    {"orderId": "517085042", "status": "FILLED", "filled": 100}
    """
    try:
        # Reuse watcher's message handler
        penny_stock_watcher.penny_stock_watcher._handle_order_message(payload)
        return {"simulated": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/ibkr/positions')
async def ibkr_positions():
    """Return formatted IBKR positions (conid, symbol, position, avgPrice) for diagnostics."""
    try:
        ib = ibkr_service
        fmt = await asyncio.to_thread(ib.get_formatted_positions)
        # return a compact view
        compact = [
            {
                'conid': p.get('conid') or p.get('contractId') or p.get('conId'),
                'symbol': p.get('symbol') or p.get('contractDesc') or p.get('ticker'),
                'position': p.get('position'),
                'avgPrice': p.get('avgPrice') or p.get('avgCost'),
                'currentPrice': p.get('currentPrice') or p.get('mktPrice') or p.get('last')
            }
            for p in fmt
        ]
        return {'count': len(compact), 'positions': compact}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/ibkr/orders')
async def ibkr_orders():
    """Return current open orders from IBKR (WS cache if present, else REST)."""
    try:
        ib = ibkr_service
        # Prefer websocket cached orders if available (run blocking call in thread)
        orders = await asyncio.to_thread(ib.get_orders_data)
        if not orders:
            # Fall back to REST endpoint if client supports it
            try:
                def rest_call():
                    if hasattr(ib.client, 'get_orders'):
                        resp = ib.client.get_orders()
                        return resp.data if resp and hasattr(resp, 'data') else resp
                    return None
                orders = await asyncio.to_thread(rest_call)
            except Exception:
                orders = None

        return {'count': len(orders) if orders else 0, 'orders': orders or []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/penny-watcher/reconcile')
async def penny_watcher_reconcile():
    """Admin endpoint to force reconciliation between IBKR orders and stored parent orders."""
    try:
        watcher = penny_stock_watcher.penny_stock_watcher
        if not hasattr(watcher, 'reconcile_with_rest'):
            raise Exception('Reconcile not implemented')
        res = await asyncio.to_thread(watcher.reconcile_with_rest)
        return {'reconciled': True, 'summary': res}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/ibkr/ws-logging')
async def ibkr_ws_logging(enable: bool = True):
    """Toggle runtime websocket orders logging on/off.

    Call with ?enable=true or ?enable=false. Returns current state.
    """
    try:
        ib = ibkr_service
        ok = await asyncio.to_thread(ib.set_runtime_ws_logging, bool(enable))
        return {'ok': ok, 'enabled': bool(enable)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/order-tracking")
def order_tracking_status() -> Dict[str, Any]:
    """Get status and statistics of the order tracking service"""
    try:
        return order_tracking_service.get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/order-tracking/reconcile")
def force_reconcile_orders() -> Dict[str, Any]:
    """Force reconciliation of current IBKR orders with stored alerts"""
    try:
        return order_tracking_service.force_reconcile()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/order-tracking/test")
async def test_order_update(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Test the order tracking service with a simulated order update"""
    try:
        # Process the message directly
        await order_tracking_service._process_order_message(payload)
        return {"status": "Test order message processed", "payload": payload}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/alerts/cleanup")
def cleanup_stale_alerts(hours_old: int = Query(24, ge=1, le=168)) -> Dict[str, Any]:
    """
    Manually trigger cleanup of stale alerts that haven't been marked as open
    
    IMPORTANT: Only removes alerts with open=false or missing open field.
    Never removes alerts with open=true (those are live positions removed only by order updates).
    
    Query params:
    - hours_old: Remove non-open alerts older than this many hours (default: 24, max: 168/1 week)
    """
    try:
        _cleanup_stale_alerts(hours_old=hours_old)
        return {
            "status": "Cleanup completed", 
            "hours_old": hours_old,
            "message": f"Removed non-open alerts older than {hours_old} hours (open=true alerts preserved)"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/alerts/clear-all")
def clear_all_alerts() -> Dict[str, Any]:
    """
    ⚠️ DANGER: Clear ALL stored alerts completely
    
    This endpoint removes ALL alerts regardless of their status (open=true or open=false).
    
    ⚠️ WARNING: This is a destructive operation that cannot be undone!
    
    Use cases:
    - Testing and development
    - System maintenance/reset
    - Emergency cleanup
    
    Returns detailed breakdown of what was cleared.
    """
    try:
        result = _clear_all_alerts()
        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
