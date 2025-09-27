def get_us_stock_exchanges() -> set:
    """Return a set of common US stock exchanges for validation and IBKR API lookup."""
    return {
        "NYSE", "NASDAQ", "AMEX", "ARCA", "BATS", "IEX", "OTC", "CBOE", "NYS", "NSD"
    }
"""
Utility functions for data parsing and manipulation
"""
from typing import Dict, Any


def parse_position_data(market_data: Dict[str, Any]) -> Dict[str, Any]:
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


def format_error_response(message: str, status_code: int = 500) -> Dict[str, Any]:
    """Format error response consistently"""
    return {"error": message}


def format_success_response(data: Any, message: str = None) -> Dict[str, Any]:
    """Format success response consistently"""
    response = {"success": True}
    if message:
        response["message"] = message
    if data is not None:
        response["data"] = data
    return response
