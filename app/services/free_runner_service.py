"""
Free Runner tracking service for monitoring position price targets
"""
from typing import Dict, Any, Optional
import asyncio
from .ibkr_service import ibkr_service


class FreeRunnerService:
    """Service for managing free runner tracking orders"""
    
    def __init__(self):
        self.free_runners: Dict[int, Dict[str, Any]] = {}
    
    def create_free_runner(self, conid: int, target_price: float) -> Dict[str, Any]:
        """Create a free runner tracking order"""
        # Find the position
        target_position = ibkr_service.find_position_by_conid(conid)
        
        if not target_position:
            raise ValueError(f"No open position found for conid {conid}")
        
        # Determine if it's a long or short position
        position_size = target_position.get("position", 0)
        is_long = position_size > 0
        current_price = target_position.get("mktPrice", 0)
        
        # Store the free runner tracking order
        import time
        self.free_runners[conid] = {
            "target_price": target_price,
            "is_long": is_long,
            "position_size": position_size,
            "start_price": current_price,
            "start_time": time.time(),  # Use time.time() instead of asyncio event loop
            "symbol": target_position.get("contractDesc"),
            "status": "active"
        }
        
        return {
            "conid": conid,
            "target_price": target_price,
            "current_price": current_price,
            "position_size": position_size,
            "is_long": is_long,
            "symbol": target_position.get("contractDesc")
        }
    
    def get_active_runners(self) -> Dict[int, Dict[str, Any]]:
        """Get all active free runners"""
        return {conid: runner for conid, runner in self.free_runners.items() 
                if runner.get("status") == "active"}
    
    def complete_runner(self, conid: int, reason: str):
        """Mark a free runner as completed"""
        if conid in self.free_runners:
            self.free_runners[conid]["status"] = "completed"
    
    def check_runner_conditions(self, current_positions: list) -> list:
        """Check if any free runners have met their conditions"""
        completed_events = []
        position_conids = {pos.get("conid") for pos in current_positions if pos.get("position", 0) != 0}
        
        for conid, runner_info in self.get_active_runners().items():
            target_price = runner_info["target_price"]
            is_long = runner_info.get("is_long", True)
            
            # Check if position still exists
            if conid not in position_conids:
                completed_events.append({
                    "type": "free_runner_completed",
                    "data": {
                        "conid": conid,
                        "reason": "position_closed",
                        "target_price": target_price,
                        "symbol": runner_info.get("symbol"),
                        "message": f"Position closed before reaching target price {target_price}"
                    }
                })
                self.complete_runner(conid, "position_closed")
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
                # For long positions, place a trailing stop sell order
                order_result = None
                trailing_amount = None
                
                if is_long:
                    try:
                        # Get the original entry price from the position
                        entry_price = current_pos.get("avgPrice", 0)
                        
                        if entry_price > 0:
                            # Calculate the gain from entry to target
                            price_gain = target_price - entry_price
                            
                            # Set trailing stop at 10% of the gain below the target price
                            # This preserves 90% of the gain from the original entry point
                            trailing_amount = price_gain * 0.10
                            
                            # Ensure trailing amount is positive and reasonable
                            if trailing_amount <= 0:
                                # Fallback: use 2% of target price if calculation results in negative/zero
                                trailing_amount = target_price * 0.02
                        else:
                            # Fallback: use 2% of target price if we can't get entry price
                            trailing_amount = target_price * 0.02
                        
                        # Place trailing limit order for the current position size
                        # Use a small limit offset (1 cent) to ensure execution while allowing extended hours
                        order_result = ibkr_service.place_trailing_limit_order(
                            conid=conid,
                            quantity=abs(current_pos.get("position", 0)),
                            trailing_amount=trailing_amount,
                            limit_offset=0.01  # 1 cent limit offset for better execution
                        )
                        
                    except Exception as e:
                        # Log the error but continue with the completion event
                        print(f"Failed to place trailing limit order for conid {conid}: {str(e)}")
                
                completed_events.append({
                    "type": "free_runner_completed",
                    "data": {
                        "conid": conid,
                        "reason": "target_reached",
                        "target_price": target_price,
                        "current_price": current_price,
                        "position": current_pos,
                        "symbol": runner_info.get("symbol"),
                        "message": f"Target price {target_price} reached! Current price: {current_price}",
                        "is_long": is_long,
                        "trailing_limit_order": order_result if is_long else None,
                        "trailing_limit_amount": trailing_amount if is_long else None,
                        "limit_offset": 0.01 if is_long else None,
                        "extended_hours_enabled": True if is_long else None,
                        "entry_price": current_pos.get("avgPrice", 0) if is_long else None,
                        "gain_preserved": f"{90}%" if is_long and trailing_amount else None
                    }
                })
                self.complete_runner(conid, "target_reached")
        
        return completed_events


# Global instance
free_runner_service = FreeRunnerService()
