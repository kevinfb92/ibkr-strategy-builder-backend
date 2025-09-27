
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from ibind import IbkrClient, IbkrWsClient, IbkrWsKey
import asyncio
from typing import Dict, List, Any, Optional

print("checking ibind:")
# Construct the client
client = IbkrClient()

# Call some endpoints
print('\n#### check_health ####')
print(client.check_health())

print('\n\n#### tickle ####')
print(client.tickle().data)

print('\n\n#### get_accounts ####')
print(client.portfolio_accounts().data)

ws_client = IbkrWsClient(ibkr_client=client, start=True)

def parse_position_data(market_data):
    """Parse market data and extract key position metrics"""
    if not market_data:
        return {}
    
    parsed = {
        "timestamp": market_data.get("timestamp"),
        "conid": market_data.get("conid")
    }
    
    # Map the important field numbers to readable names
    field_mappings = {
        "31": "lastPrice",          # Last Price
        "70": "dayHigh",            # Current day high
        "71": "dayLow",             # Current day low  
        "73": "marketValue",        # Market Value of position
        "74": "avgPrice",           # Average cost price
        "75": "unrealizedPnl",      # Unrealized P&L
        "78": "dailyPnl",           # Daily P&L since prior close
        "79": "realizedPnl",        # Realized P&L
        "80": "unrealizedPnlPct",   # Unrealized P&L %
        "82": "priceChange",        # Price change from prior close
        "83": "priceChangePct",     # Price change % from prior close
        "7741": "priorClose",       # Prior close price
    }
    
    # Extract and convert the fields
    for field_num, field_name in field_mappings.items():
        if field_num in market_data:
            value = market_data[field_num]
            # Convert to float if it's a numeric string
            try:
                parsed[field_name] = float(value) if isinstance(value, str) and value.replace('.', '').replace('-', '').isdigit() else value
            except (ValueError, AttributeError):
                parsed[field_name] = value
    
    return parsed


app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/echo")
def echo(data: dict):
    return JSONResponse(content={"echo": data})

@app.post("/free-runner")
def create_free_runner(data: dict):
    """Create a free runner tracking order for a stock position"""
    try:
        conid = data.get("conid")
        target_price = data.get("price")
        
        if not conid or not target_price:
            return JSONResponse(
                content={"error": "Missing required fields: conid and price"}, 
                status_code=400
            )
        
        # Validate conid is integer and price is float
        try:
            conid = int(conid)
            target_price = float(target_price)
        except (ValueError, TypeError):
            return JSONResponse(
                content={"error": "Invalid data types: conid must be integer, price must be number"}, 
                status_code=400
            )
        
        # Check if we have a position in this stock
        accounts = client.portfolio_accounts().data
        if not accounts or not isinstance(accounts, list) or len(accounts) == 0:
            return JSONResponse(content={"error": "No accounts found"}, status_code=404)
        
        account_id = accounts[0]["accountId"]
        client.switch_account(account_id)
        positions = client.positions().data
        
        # Find the position
        target_position = None
        for pos in positions:
            if pos.get("conid") == conid and pos.get("position", 0) != 0:
                target_position = pos
                break
        
        if not target_position:
            return JSONResponse(
                content={"error": f"No open position found for conid {conid}"}, 
                status_code=404
            )
        
        # Determine if it's a long or short position
        position_size = target_position.get("position", 0)
        is_long = position_size > 0
        current_price = target_position.get("mktPrice", 0)
        
        # Store the free runner tracking order in a global dict (for simplicity)
        # In production, you'd want to use a database
        if not hasattr(app.state, 'free_runners'):
            app.state.free_runners = {}
        
        app.state.free_runners[conid] = {
            "target_price": target_price,
            "is_long": is_long,
            "position_size": position_size,
            "start_price": current_price,
            "start_time": asyncio.get_event_loop().time(),
            "symbol": target_position.get("contractDesc"),
            "status": "active"
        }
        
        return JSONResponse(content={
            "success": True,
            "message": f"Free runner created for {target_position.get('contractDesc')}",
            "data": {
                "conid": conid,
                "target_price": target_price,
                "current_price": current_price,
                "position_size": position_size,
                "is_long": is_long,
                "symbol": target_position.get("contractDesc")
            }
        })
        
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/positions")
def get_positions():
    """Get current positions to know which contracts to subscribe to for P&L"""
    try:
        # Get account information first
        accounts = client.portfolio_accounts().data
        if not accounts or not isinstance(accounts, list) or len(accounts) == 0:
            return JSONResponse(content={"error": "No accounts found"}, status_code=404)
        
        account_id = accounts[0]["accountId"]  # Use first account's accountId
        
        # Switch to the account and get positions
        client.switch_account(account_id)
        positions = client.positions().data
        
        # Return simplified position data with contract IDs for subscription
        simplified_positions = []
        for pos in positions:
            pos: Dict[str, Any]  # Type hint for position dictionary
            simplified_positions.append({
                "conid": pos.get("conid"),
                "symbol": pos.get("contractDesc"),
                "position": pos.get("position"),
                "avgCost": pos.get("avgCost"),
                "avgPrice": pos.get("avgPrice"),
                "mktPrice": pos.get("mktPrice"),
                "mktValue": pos.get("mktValue"),
                "unrealizedPnl": pos.get("unrealizedPnl"),
                "realizedPnl": pos.get("realizedPnl"),
                "currency": pos.get("currency"),
                "secType": pos.get("assetClass"),  # Use assetClass field for security type
                "description": pos.get("contractDesc")
            })
        
        return JSONResponse(content={"positions": simplified_positions})
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)



@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # Store active subscriptions for this connection
    active_subs = {}
    # Store last positions data to detect changes
    last_positions_data = {}
    # Store polling task references
    positions_task = None
    orders_task = None
    # Store free runner tracking orders
    free_runners: Dict[int, Dict[str, Any]] = {}  # conid -> {target_price, start_time, etc}
    free_runner_task = None

    try:
        async def get_positions_snapshot():
            """Get current positions snapshot from IBKR API"""
            try:
                accounts = client.portfolio_accounts().data
                if not accounts or not isinstance(accounts, list) or len(accounts) == 0:
                    return []
                
                account_id = accounts[0]["accountId"]  # Use first account's accountId
                
                # Switch to the account and get positions
                client.switch_account(account_id)
                positions_response = client.positions().data
                
                # The positions response should be a list of position dictionaries
                if not isinstance(positions_response, list):
                    await websocket.send_json({"type": "debug", "message": f"Unexpected positions structure: {type(positions_response)}, content: {positions_response}"})
                    return []
                
                positions = positions_response
                
                # Return the positions with all the P&L data already calculated by IBKR
                formatted_positions = []
                for pos in positions:
                    pos: Dict[str, Any]  # Type hint for position dictionary
                    # Handle both dict access and list access
                    if isinstance(pos, dict):
                        formatted_position = {
                            "conid": pos.get("conid"),
                            "symbol": pos.get("contractDesc"),
                            "position": pos.get("position"),
                            "avgCost": pos.get("avgCost"),
                            "avgPrice": pos.get("avgPrice"),
                            "currentPrice": pos.get("mktPrice"),
                            "marketValue": pos.get("mktValue"),
                            "unrealizedPnl": pos.get("unrealizedPnl"),
                            "realizedPnl": pos.get("realizedPnl"),
                            "currency": pos.get("currency"),
                            "secType": pos.get("assetClass"),  # Use assetClass field for security type
                            "description": pos.get("contractDesc"),
                            # Calculate percentage if not provided
                            "unrealizedPnlPct": (pos.get("unrealizedPnl", 0) / abs(pos.get("mktValue", 1))) * 100 if pos.get("mktValue") else 0,
                            "dailyPnl": pos.get("unrealizedPnl", 0),  # Using unrealized as daily for now
                            "priceChange": pos.get("mktPrice", 0) - pos.get("avgPrice", 0) if pos.get("mktPrice") and pos.get("avgPrice") else 0
                        }
                        formatted_positions.append(formatted_position)
                    else:
                        await websocket.send_json({"type": "debug", "message": f"Position item is not dict: {type(pos)}, content: {pos}"})
                
                return formatted_positions
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
                    if not ws_client.empty(IbkrWsKey.ORDERS):
                        data = ws_client.get(IbkrWsKey.ORDERS)
                        await websocket.send_json({"type": "orders", "data": data})
                    
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
                    # Get free runners from app state
                    if not hasattr(app.state, 'free_runners') or not app.state.free_runners:
                        await asyncio.sleep(1.0)
                        continue
                    
                    # Get current positions to check if we still have positions
                    current_positions = await get_positions_snapshot()
                    position_conids = {pos.get("conid") for pos in current_positions if pos.get("position", 0) != 0}
                    
                    # Check each free runner
                    completed_runners = []
                    for conid, runner_info in app.state.free_runners.items():
                        if runner_info.get("status") != "active":
                            continue
                            
                        target_price = runner_info["target_price"]
                        is_long = runner_info.get("is_long", True)
                        
                        # Check if position still exists
                        if conid not in position_conids:
                            await websocket.send_json({
                                "type": "free_runner_completed",
                                "data": {
                                    "conid": conid,
                                    "reason": "position_closed",
                                    "target_price": target_price,
                                    "symbol": runner_info.get("symbol"),
                                    "message": f"Position closed before reaching target price {target_price}"
                                }
                            })
                            runner_info["status"] = "completed"
                            completed_runners.append(conid)
                            continue
                        
                        # Get current position data
                        current_pos = next((pos for pos in current_positions if pos.get("conid") == conid), None)
                        if not current_pos:
                            continue
                            
                        current_price = current_pos.get("currentPrice", 0)
                        if not current_price:
                            continue
                        
                        # Check if target price is reached
                        target_reached = False
                        if is_long and current_price >= target_price:
                            target_reached = True
                        elif not is_long and current_price <= target_price:
                            target_reached = True
                        
                        if target_reached:
                            await websocket.send_json({
                                "type": "free_runner_completed",
                                "data": {
                                    "conid": conid,
                                    "reason": "target_reached",
                                    "target_price": target_price,
                                    "current_price": current_price,
                                    "position": current_pos,
                                    "symbol": runner_info.get("symbol"),
                                    "message": f"Target price {target_price} reached! Current price: {current_price}"
                                }
                            })
                            runner_info["status"] = "completed"
                            completed_runners.append(conid)
                    
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
            symbol = msg.get("symbol")

            if action == "subscribe":
                if sub_type == "positions" and "positions" not in active_subs:
                    # Start position polling
                    active_subs["positions"] = True
                    if positions_task is None or positions_task.done():
                        positions_task = asyncio.create_task(poll_positions())
                    await websocket.send_json({"type": "message", "data": "Subscribed to positions summary"})
                elif sub_type == "orders" and "orders" not in active_subs:
                    # Start order subscription and polling
                    ws_client.subscribe(channel=IbkrWsKey.ORDERS.channel)
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

            elif action == "unsubscribe":
                if sub_type == "positions" and "positions" in active_subs:
                    del active_subs["positions"]
                    # Stop position polling
                    if positions_task and not positions_task.done():
                        positions_task.cancel()
                        positions_task = None
                    await websocket.send_json({"type": "message", "data": "Unsubscribed from positions summary"})
                elif sub_type == "orders" and "orders" in active_subs:
                    ws_client.unsubscribe(IbkrWsKey.ORDERS)
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

    except WebSocketDisconnect:
        # Cancel all polling tasks on disconnect
        if positions_task and not positions_task.done():
            positions_task.cancel()
        if orders_task and not orders_task.done():
            orders_task.cancel()
        if free_runner_task and not free_runner_task.done():
            free_runner_task.cancel()
        
        # Unsubscribe from orders if subscribed
        if "orders" in active_subs:
            ws_client.unsubscribe(IbkrWsKey.ORDERS)
        pass

# ibind_logs_initialize()  # Remove or comment out if not needed


