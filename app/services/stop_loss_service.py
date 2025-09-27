"""
Stop Loss Management Service

This service monitors positions and automatically adjusts stop-limit orders
when the position's unrealized PnL percentage reaches a specified threshold.
"""

import time
import threading
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

from .ibkr_service import ibkr_service


@dataclass
class StopLossConfig:
    """Configuration for stop loss management"""
    conid: int
    percentage: float  # PnL percentage threshold to trigger adjustment
    created_at: datetime
    status: str = "active"  # active, paused, completed


class StopLossManagementService:
    """Service to manage stop loss orders based on PnL thresholds"""
    
    def __init__(self):
        self._active_configs: Dict[int, StopLossConfig] = {}
        self._monitoring_thread: Optional[threading.Thread] = None
        self._monitoring_active = False
        self._check_interval = 30  # Check every 30 seconds
        
    def create_stop_loss_management(self, conid: int, percentage: float) -> Dict[str, Any]:
        """
        Create a new stop loss management configuration
        
        Args:
            conid: Contract ID to monitor
            percentage: PnL percentage threshold (e.g., 5.0 for 5%)
            
        Returns:
            Dict with configuration details and validation results
        """
        try:
            # Validate that position exists
            position = ibkr_service.find_position_by_conid(conid)
            if not position:
                raise ValueError(f"No open position found for conid {conid}")
            
            position_size = position.get("position", 0)
            if position_size == 0:
                raise ValueError(f"Position size is zero for conid {conid}")
            
            # Check for existing stop-limit orders (excluding trailing orders)
            stop_limit_orders = self._get_stop_limit_orders(conid)
            if not stop_limit_orders:
                raise ValueError(f"No stop-limit orders found for conid {conid}")
            
            # Create configuration
            config = StopLossConfig(
                conid=conid,
                percentage=percentage,
                created_at=datetime.now(),
                status="active"
            )
            
            # Store configuration
            self._active_configs[conid] = config
            
            # Start monitoring if not already running
            if not self._monitoring_active:
                self._start_monitoring()
            
            return {
                "success": True,
                "config": {
                    "conid": conid,
                    "percentage": percentage,
                    "created_at": config.created_at.isoformat(),
                    "status": config.status
                },
                "position": {
                    "symbol": position.get("contractDesc"),
                    "size": position_size,
                    "avg_price": position.get("avgPrice"),
                    "current_price": position.get("mktPrice"),
                    "unrealized_pnl": position.get("unrealizedPnl"),
                    "unrealized_pnl_pct": position.get("unrealizedPnl", 0) / abs(position.get("mktValue", 1)) * 100
                },
                "stop_limit_orders": len(stop_limit_orders),
                "message": f"Stop loss management activated for {position.get('contractDesc')} at {percentage}% PnL threshold"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def _get_stop_limit_orders(self, conid: int) -> List[Dict[str, Any]]:
        """Get all stop-limit orders for a contract (excluding trailing orders)"""
        try:
            client = ibkr_service.client
            orders_response = client.live_orders()
            
            if not hasattr(orders_response, 'data') or 'orders' not in orders_response.data:
                return []
            
            orders = orders_response.data['orders']
            
            # Filter for stop-limit orders for this conid (exclude trailing orders)
            stop_limit_orders = []
            for order in orders:
                if (order.get('conid') == conid and 
                    order.get('orderType') in ['STP_LMT', 'STOP_LIMIT'] and
                    'TRAIL' not in order.get('orderType', '') and
                    order.get('status') not in ['Cancelled', 'Filled']):
                    stop_limit_orders.append(order)
            
            return stop_limit_orders
            
        except Exception as e:
            print(f"Error getting stop-limit orders for conid {conid}: {e}")
            return []
    
    def _start_monitoring(self):
        """Start the background monitoring thread"""
        if self._monitoring_active:
            return
            
        self._monitoring_active = True
        self._monitoring_thread = threading.Thread(target=self._monitor_positions, daemon=True)
        self._monitoring_thread.start()
        print("Stop loss monitoring started")
    
    def _monitor_positions(self):
        """Background monitoring loop"""
        while self._monitoring_active:
            try:
                # Check each active configuration
                configs_to_remove = []
                
                for conid, config in self._active_configs.items():
                    if config.status != "active":
                        continue
                        
                    try:
                        # Check if position still exists
                        position = ibkr_service.find_position_by_conid(conid)
                        if not position or position.get("position", 0) == 0:
                            print(f"Position closed for conid {conid}, removing from monitoring")
                            configs_to_remove.append(conid)
                            continue
                        
                        # Calculate current PnL percentage
                        unrealized_pnl = position.get("unrealizedPnl", 0)
                        market_value = position.get("mktValue", 0)
                        
                        if market_value != 0:
                            current_pnl_pct = (unrealized_pnl / abs(market_value)) * 100
                            
                            print(f"Monitoring conid {conid}: PnL {current_pnl_pct:.2f}%, threshold {config.percentage}%")
                            
                            # Check if threshold is reached
                            if current_pnl_pct >= config.percentage:
                                print(f"PnL threshold reached for conid {conid}! Adjusting stop-limit orders...")
                                self._adjust_stop_limit_orders(conid, position)
                                config.status = "completed"
                        
                    except Exception as e:
                        print(f"Error monitoring position {conid}: {e}")
                
                # Remove completed configurations
                for conid in configs_to_remove:
                    del self._active_configs[conid]
                
                # If no active configurations, stop monitoring
                if not any(config.status == "active" for config in self._active_configs.values()):
                    print("No active stop loss configurations, stopping monitoring")
                    self._monitoring_active = False
                    break
                
                # Wait before next check
                time.sleep(self._check_interval)
                
            except Exception as e:
                print(f"Error in monitoring loop: {e}")
                time.sleep(self._check_interval)
    
    def _adjust_stop_limit_orders(self, conid: int, position: Dict[str, Any]):
        """Adjust stop-limit orders to break-even (entry price)"""
        try:
            # Get entry price (average cost)
            entry_price = position.get("avgPrice", 0)
            if not entry_price:
                print(f"Cannot adjust orders: no entry price for conid {conid}")
                return
            
            # Get stop-limit orders
            stop_limit_orders = self._get_stop_limit_orders(conid)
            if not stop_limit_orders:
                print(f"No stop-limit orders to adjust for conid {conid}")
                return
            
            print(f"Adjusting {len(stop_limit_orders)} stop-limit orders to break-even price ${entry_price}")
            
            for order in stop_limit_orders:
                try:
                    order_id = order.get('orderId')
                    current_stop_price = order.get('auxPrice', 0)
                    current_limit_price = order.get('price', 0)
                    
                    # Calculate new limit price (entry price minus small offset for execution)
                    new_stop_price = round(entry_price, 2)
                    new_limit_price = round(entry_price - 0.01, 2)  # 1 cent below for execution
                    
                    print(f"Order {order_id}: Stop ${current_stop_price} -> ${new_stop_price}, Limit ${current_limit_price} -> ${new_limit_price}")
                    
                    # Modify the order
                    self._modify_stop_limit_order(order_id, new_stop_price, new_limit_price)
                    
                except Exception as e:
                    print(f"Error adjusting order {order.get('orderId')}: {e}")
            
        except Exception as e:
            print(f"Error adjusting stop-limit orders for conid {conid}: {e}")
    
    def _modify_stop_limit_order(self, order_id: str, new_stop_price: float, new_limit_price: float):
        """Modify a stop-limit order with new prices"""
        try:
            client = ibkr_service.client
            
            # IBKR modify order payload
            modify_payload = {
                "orderId": order_id,
                "auxPrice": new_stop_price,  # Stop price
                "price": new_limit_price     # Limit price
            }
            
            result = client.modify_order(order_id, **modify_payload)
            print(f"Order {order_id} modified successfully: {result}")
            
        except Exception as e:
            print(f"Error modifying order {order_id}: {e}")
            raise
    
    def get_active_configurations(self) -> Dict[str, Any]:
        """Get all active stop loss configurations"""
        return {
            "active_configs": [
                {
                    "conid": config.conid,
                    "percentage": config.percentage,
                    "created_at": config.created_at.isoformat(),
                    "status": config.status
                }
                for config in self._active_configs.values()
            ],
            "monitoring_active": self._monitoring_active,
            "check_interval": self._check_interval
        }
    
    def remove_configuration(self, conid: int) -> Dict[str, Any]:
        """Remove a stop loss configuration"""
        if conid in self._active_configs:
            config = self._active_configs.pop(conid)
            return {
                "success": True,
                "message": f"Stop loss configuration removed for conid {conid}",
                "removed_config": {
                    "conid": config.conid,
                    "percentage": config.percentage,
                    "status": config.status
                }
            }
        else:
            return {
                "success": False,
                "error": f"No active configuration found for conid {conid}"
            }
    
    def stop_monitoring(self):
        """Stop all monitoring"""
        self._monitoring_active = False
        self._active_configs.clear()
        print("Stop loss monitoring stopped")


# Global instance
stop_loss_management_service = StopLossManagementService()
