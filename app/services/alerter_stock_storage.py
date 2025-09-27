"""
Stock storage service for tracking alerted stocks across different alerters
"""
import json
import os
import logging
from app.services.ibkr_service import IBKRService
from typing import Dict, Any, List, Optional, Set
from datetime import datetime

logger = logging.getLogger(__name__)

class AlerterStockStorage:
    """Service for storing and managing alerted stocks per alerter"""

    def __init__(self, storage_file: str = "alerter_stocks.json"):
        self.storage_file = storage_file
        self.storage_path = os.path.join(os.getcwd(), "data", storage_file)
        self._ensure_storage_directory()
        self.stocks = self._load_stocks()

    def _ensure_storage_directory(self):
        """Ensure the data directory exists"""
        data_dir = os.path.dirname(self.storage_path)
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
            logger.info(f"Created data directory: {data_dir}")

    def _load_stocks(self) -> Dict[str, Dict[str, Any]]:
        """Load stocks from storage file"""
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, 'r') as f:
                    data = json.load(f)
                    logger.info(f"Loaded alerted stocks from {self.storage_path}")
                    return data
            else:
                logger.info(f"No existing stocks file found at {self.storage_path}")
                return {}
        except Exception as e:
            logger.error(f"Error loading stocks: {e}")
            return {}
    
    def _save_stocks(self):
        """Save stocks to storage file"""
        try:
            with open(self.storage_path, 'w') as f:
                json.dump(self.stocks, f, indent=2, default=str)
            logger.info(f"Saved alerted stocks to {self.storage_path}")
        except Exception as e:
            logger.error(f"Error saving stocks: {e}")
    
    def remove_stock_alert(self, alerter_name: str, ticker: str) -> bool:
        """
        Completely remove a stock alert from storage
        Args:
            alerter_name: Name of the alerter
            ticker: Stock ticker symbol
        Returns:
            True if removed successfully, False if not found or error
        """

        if alerter_name not in self.stocks:
            return False
        if ticker not in self.stocks[alerter_name]:
            return False
        del self.stocks[alerter_name][ticker]
        # Clean up empty alerter entries
        if not self.stocks[alerter_name]:
            del self.stocks[alerter_name]
        self._save_stocks()
        logger.info(f"Removed stock alert for {alerter_name}: {ticker}")
        return True

    def get_total_open_contracts(self, alerter_name: str) -> Dict[str, Any]:
        """
        For Real Day Trading: Return a summary of open option contracts for tickers stored for the alerter using IBKR positions.
        Includes total contract count, and a list of contracts with symbol, strike, side, quantity, and P/L info.
        """
        if alerter_name not in self.stocks:
            return {"total_contracts": 0, "contracts": []}
        tickers = set(self.stocks[alerter_name].keys())
        ibkr = IBKRService()
        positions = ibkr.get_positions()
        contracts = []
        total_contracts = 0
        for pos in positions:
            sec_type = pos.get("assetClass") or pos.get("secType")
            symbol = pos.get("contractDesc") or pos.get("symbol")
            position_qty = abs(int(pos.get("position", 0)))
            # Option contracts
            if sec_type and sec_type.upper() == "OPT" and symbol and position_qty > 0:
                for ticker in tickers:
                    if ticker and symbol and ticker.upper() in symbol.upper():
                        parts = symbol.split()
                        strike = None
                        side = None
                        for part in parts:
                            if part.replace('.', '', 1).isdigit():
                                strike = part
                            elif part.upper() in ["C", "P"]:
                                side = "CALL" if part.upper() == "C" else "PUT"
                        contracts.append({
                            "symbol": symbol,
                            "ticker": ticker,
                            "strike": strike,
                            "side": side,
                            "quantity": position_qty,
                            "unrealizedPnl": pos.get("unrealizedPnl"),
                            "realizedPnl": pos.get("realizedPnl"),
                            "marketValue": pos.get("mktValue"),
                            "avgPrice": pos.get("avgPrice"),
                            "currentPrice": pos.get("mktPrice")
                        })
                        total_contracts += position_qty
                        break
            # Stock positions: add as contract entry with P/L and price info
            elif sec_type and sec_type.upper() == "STK" and symbol and position_qty > 0:
                for ticker in tickers:
                    if ticker and (ticker.upper() == symbol.upper() or ticker.upper() in symbol.upper()):
                        contracts.append({
                            "symbol": symbol,
                            "ticker": ticker,
                            "quantity": position_qty,
                            "unrealizedPnl": pos.get("unrealizedPnl"),
                            "realizedPnl": pos.get("realizedPnl"),
                            "marketValue": pos.get("mktValue"),
                            "avgPrice": pos.get("avgPrice"),
                            "currentPrice": pos.get("mktPrice")
                        })
                        total_contracts += position_qty
                        break
        return {"total_contracts": total_contracts, "contracts": contracts}

    def cleanup_old_alerts(self, days_old: int = 30):
        """
        Clean up old closed alerts (optional maintenance function)
        Args:
            days_old: Remove closed alerts older than this many days
        """
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=days_old)
        removed_count = 0
        for alerter_name in list(self.stocks.keys()):
            for ticker in list(self.stocks[alerter_name].keys()):
                stock_data = self.stocks[alerter_name][ticker]
                if stock_data.get("status") == "CLOSED":
                    closed_time_str = stock_data.get("closed_time")
                    if closed_time_str:
                        try:
                            closed_time = datetime.fromisoformat(closed_time_str.replace('Z', '+00:00'))
                            if closed_time < cutoff_date:
                                self.remove_stock_alert(alerter_name, ticker)
                                removed_count += 1
                        except ValueError:
                            continue
        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} old closed alerts")
    
    def is_stock_already_alerted(self, alerter_name: str, ticker: str) -> bool:
        """
        Check if a stock is already alerted and active for an alerter
        
        Args:
            alerter_name: Name of the alerter
            ticker: Stock ticker symbol
            
        Returns:
            True if already alerted and active, False otherwise
        """
        try:
            if alerter_name not in self.stocks:
                return False
            
            stock_data = self.stocks[alerter_name].get(ticker)
            if not stock_data:
                return False
            
            return stock_data.get("status") == "ACTIVE"
            
        except Exception as e:
            logger.error(f"Error checking if stock is alerted for {alerter_name}/{ticker}: {e}")
            return False
    
    def close_stock_alert(self, alerter_name: str, ticker: str) -> bool:
        """
        Close a stock alert (mark as closed, but keep in storage)
        This will be called when user presses the "Close" button in the bot
        
        Args:
            alerter_name: Name of the alerter
            ticker: Stock ticker symbol
            
        Returns:
            True if closed successfully, False if not found or error
        """
        try:
            if alerter_name not in self.stocks:
                logger.warning(f"No stocks found for alerter: {alerter_name}")
                return False
            
            if ticker not in self.stocks[alerter_name]:
                logger.warning(f"Stock {ticker} not found for alerter: {alerter_name}")
                return False
            
            # Mark as closed and add close timestamp
            self.stocks[alerter_name][ticker]["status"] = "CLOSED"
            self.stocks[alerter_name][ticker]["closed_time"] = datetime.now().isoformat()
            
            self._save_stocks()
            logger.info(f"Closed stock alert for {alerter_name}: {ticker}")
            return True
            
        except Exception as e:
            logger.error(f"Error closing stock alert for {alerter_name}/{ticker}: {e}")
            return False
    
    def remove_stock_alert(self, alerter_name: str, ticker: str) -> bool:
        """
        Completely remove a stock alert from storage
        
        Args:
            alerter_name: Name of the alerter
            ticker: Stock ticker symbol
            
        Returns:
            True if removed successfully, False if not found or error
        """
        try:
            if alerter_name not in self.stocks:
                return False
            
            if ticker not in self.stocks[alerter_name]:
                return False
            
            del self.stocks[alerter_name][ticker]
            
            # Clean up empty alerter entries
            if not self.stocks[alerter_name]:
                del self.stocks[alerter_name]
            return True
        except Exception as e:
            logger.error(f"Error removing stock alert for {alerter_name}/{ticker}: {e}")
            return False

    def get_total_open_contracts(self, alerter_name: str) -> int:
        """
        Get the total number of open contracts for all tickers currently stored for the given alerter.
        Sums the latest contract_count (or quantity, or defaults to 1) for each ticker.
        """

        total_contracts = 0
        if alerter_name not in self.stocks:
            return 0
        for ticker, stock_data in self.stocks[alerter_name].items():
            alert_data = stock_data.get("latest_alert_data", {})
            contract_count = alert_data.get("contract_count")
            quantity = alert_data.get("quantity")
            try:
                if contract_count is not None:
                    total_contracts += int(contract_count)
                elif quantity is not None:
                    total_contracts += int(quantity)
                else:
                    total_contracts += 1
            except Exception:
                total_contracts += 1
        return total_contracts
    

    def get_all_stocks(self) -> Dict[str, Dict[str, Any]]:
        """Get all stocks across all alerters"""
        return self.stocks.copy()

    def get_storage_stats(self) -> Dict[str, Any]:
        """Get storage statistics"""
        stats = {
            "total_alerters": len(self.stocks),
            "storage_file": self.storage_path,
            "file_exists": os.path.exists(self.storage_path),
            "alerters": {}
        }
        for alerter_name, stocks in self.stocks.items():
            active_count = sum(1 for stock in stocks.values() if stock.get("status") == "ACTIVE")
            closed_count = sum(1 for stock in stocks.values() if stock.get("status") == "CLOSED")
            stats["alerters"][alerter_name] = {
                "total_stocks": len(stocks),
                "active_stocks": active_count,
                "closed_stocks": closed_count,
                "stock_tickers": list(stocks.keys())
            }
        return stats

    def add_stock_alert(self, alerter_name: str, ticker: str, alert_data: Dict[str, Any]) -> bool:
        """
        Add or update a stock alert for a given alerter.

        Returns True if this ticker was newly added or re-activated, False if it updated
        an existing active alert or an error occurred.
        """
        try:
            if not alerter_name or not ticker:
                return False

            now_iso = datetime.now().isoformat()

            if alerter_name not in self.stocks:
                self.stocks[alerter_name] = {}

            existing = self.stocks[alerter_name].get(ticker)
            was_new = False

            # If there is no existing entry or it was closed, consider this a new alert
            if not existing or existing.get("status") != "ACTIVE":
                was_new = True
                record = {
                    "status": "ACTIVE",
                    "first_alert_time": now_iso,
                    "latest_alert_time": now_iso,
                    "latest_alert_data": alert_data
                }
            else:
                # Update existing active record
                record = existing
                record["latest_alert_time"] = now_iso
                record["latest_alert_data"] = alert_data

            self.stocks[alerter_name][ticker] = record
            # persist
            self._save_stocks()
            logger.info(f"Added/updated stock alert for {alerter_name}: {ticker}")
            return was_new
        except Exception as e:
            logger.error(f"Error adding stock alert for {alerter_name}/{ticker}: {e}")
            return False

    def get_active_stocks(self, alerter_name: str) -> List[str]:
        """
        Return a list of ticker symbols that are currently marked ACTIVE for the given alerter.
        """
        try:
            if alerter_name not in self.stocks:
                return []
            return [ticker for ticker, data in self.stocks[alerter_name].items() if data.get("status") == "ACTIVE"]
        except Exception as e:
            logger.error(f"Error getting active stocks for {alerter_name}: {e}")
            return []

    def get_alerter_stocks(self, alerter_name: str, status: Optional[str] = None) -> Dict[str, Any]:
        """
        Return all stored stocks for a given alerter. If status is provided ("ACTIVE" or "CLOSED"),
        only return stocks matching that status.
        """
        try:
            if alerter_name not in self.stocks:
                return {}
            if status is None:
                return self.stocks[alerter_name].copy()
            filtered = {t: d for t, d in self.stocks[alerter_name].items() if d.get("status") == status}
            return filtered
        except Exception as e:
            logger.error(f"Error getting alerter stocks for {alerter_name} (status={status}): {e}")
            return {}

# Global instance
alerter_stock_storage = AlerterStockStorage()
