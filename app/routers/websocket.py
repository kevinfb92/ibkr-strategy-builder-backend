"""
WebSocket route handler for real-time data subscriptions
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
from typing import Dict, Any

from ..services import ibkr_service, free_runner_service
from ..services.pnl_pubsub import pnl_pubsub
from ..models import WebSocketMessage

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Store active subscriptions for this connection
    active_subs = {}
    # Store last positions data to detect changes
    last_positions_data = {}
    # Store polling task references
    positions_task = None
    orders_task = None
    free_runner_task = None

    try:
        async def get_positions_snapshot():
            """Get current positions snapshot from IBKR API"""
            try:
                positions = ibkr_service.get_formatted_positions()
                return positions
            except Exception as e:
                await websocket.send_json({"type": "error", "message": f"Failed to get positions: {str(e)}"})
                return []

        async def poll_positions():
            """Poll positions every 5 seconds and send updates"""
            while True:
                try:
                    current_positions = await get_positions_snapshot()
                    
                    if current_positions:
                        # Send positions summary
                        total_unrealized_pnl = sum(p.get("unrealizedPnl", 0) for p in current_positions)
                        total_market_value = sum(p.get("marketValue", 0) for p in current_positions)
                        
                        await websocket.send_json({
                            "type": "positions_summary",
                            "data": {
                                "positions": current_positions,
                                "totalUnrealizedPnl": total_unrealized_pnl,
                                "totalMarketValue": total_market_value,
                                "timestamp": asyncio.get_event_loop().time()
                            }
                        })
                        
                        # Check for individual position changes and send updates
                        for pos in current_positions:
                            conid = pos.get("conid")
                            if conid:
                                # Send individual position update if data changed
                                if conid not in last_positions_data or last_positions_data[conid] != pos:
                                    await websocket.send_json({
                                        "type": "position_update",
                                        "data": pos
                                    })
                                    last_positions_data[conid] = pos.copy()
                    
                    await asyncio.sleep(5.0)  # Poll every 5 seconds
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": f"Polling error: {str(e)}"})
                    await asyncio.sleep(5.0)

        async def check_for_orders():
            """Check for orders data"""
            while True:
                try:
                    orders_data = ibkr_service.get_orders_data()
                    if orders_data:
                        await websocket.send_json({"type": "orders", "data": orders_data})
                    
                    await asyncio.sleep(0.1)  # Check orders more frequently
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": f"Orders polling error: {str(e)}"})
                    await asyncio.sleep(0.1)

        async def check_free_runners():
            """Monitor free runner tracking orders"""
            while True:
                try:
                    # Get current positions to check conditions
                    current_positions = await get_positions_snapshot()
                    
                    # Check free runner conditions
                    completed_events = free_runner_service.check_runner_conditions(current_positions)
                    
                    # Send completion events
                    for event in completed_events:
                        await websocket.send_json(event)
                    
                    await asyncio.sleep(2.0)  # Check every 2 seconds for price targets
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    await websocket.send_json({"type": "error", "message": f"Free runner error: {str(e)}"})
                    await asyncio.sleep(2.0)

        while True:
            msg = await websocket.receive_json()
            action = msg.get("action")
            sub_type = msg.get("type")

            if action == "subscribe":
                if sub_type == "positions" and "positions" not in active_subs:
                    # Start position polling
                    active_subs["positions"] = True
                    if positions_task is None or positions_task.done():
                        positions_task = asyncio.create_task(poll_positions())
                    await websocket.send_json({"type": "message", "data": "Subscribed to positions summary"})
                    
                elif sub_type == "orders" and "orders" not in active_subs:
                    # Start order subscription and polling
                    ibkr_service.subscribe_orders()
                    active_subs["orders"] = True
                    if orders_task is None or orders_task.done():
                        orders_task = asyncio.create_task(check_for_orders())
                    await websocket.send_json({"type": "message", "data": "Subscribed to orders"})
                    
                elif sub_type == "free_runners" and "free_runners" not in active_subs:
                    # Start free runner monitoring
                    active_subs["free_runners"] = True
                    if free_runner_task is None or free_runner_task.done():
                        free_runner_task = asyncio.create_task(check_free_runners())
                    await websocket.send_json({"type": "message", "data": "Subscribed to free runner monitoring"})

                elif sub_type == "penny_pnl":
                    # subscribe to live P/L updates for a parent_order_id
                    parent_order_id = msg.get("parent_order_id")
                    if parent_order_id:
                        await pnl_pubsub.subscribe(parent_order_id, websocket)
                        # track subscriptions locally for cleanup
                        active_subs.setdefault("penny_pnl", set()).add(parent_order_id)
                        await websocket.send_json({"type": "message", "data": f"Subscribed to penny_pnl {parent_order_id}"})

            elif action == "unsubscribe":
                if sub_type == "positions" and "positions" in active_subs:
                    del active_subs["positions"]
                    # Stop position polling
                    if positions_task and not positions_task.done():
                        positions_task.cancel()
                        positions_task = None
                    await websocket.send_json({"type": "message", "data": "Unsubscribed from positions summary"})
                    
                elif sub_type == "orders" and "orders" in active_subs:
                    ibkr_service.unsubscribe_orders()
                    del active_subs["orders"]
                    # Stop order polling
                    if orders_task and not orders_task.done():
                        orders_task.cancel()
                        orders_task = None
                    await websocket.send_json({"type": "message", "data": "Unsubscribed from orders"})
                    
                elif sub_type == "free_runners" and "free_runners" in active_subs:
                    del active_subs["free_runners"]
                    # Stop free runner monitoring
                    if free_runner_task and not free_runner_task.done():
                        free_runner_task.cancel()
                        free_runner_task = None
                    await websocket.send_json({"type": "message", "data": "Unsubscribed from free runner monitoring"})

                elif sub_type == "penny_pnl" and "penny_pnl" in active_subs:
                    parent_order_id = msg.get("parent_order_id")
                    if parent_order_id:
                        await pnl_pubsub.unsubscribe(parent_order_id, websocket)
                        try:
                            active_subs["penny_pnl"].discard(parent_order_id)
                        except Exception:
                            pass
                        await websocket.send_json({"type": "message", "data": f"Unsubscribed from penny_pnl {parent_order_id}"})

    except WebSocketDisconnect:
        # Cancel all polling tasks on disconnect
        tasks_to_cancel = [positions_task, orders_task, free_runner_task]
        for task in tasks_to_cancel:
            if task and not task.done():
                task.cancel()
        
        # Unsubscribe from orders if subscribed
        if "orders" in active_subs:
            ibkr_service.unsubscribe_orders()
        pass
