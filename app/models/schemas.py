"""
Pydantic models for request/response validation
"""
from pydantic import BaseModel, Field
from typing import Optional, Any, Dict


class FreeRunnerRequest(BaseModel):
    """Request model for creating a free runner tracking order"""
    conid: int = Field(..., description="Contract ID of the position to track")
    price: float = Field(..., description="Target price to monitor")


class EchoRequest(BaseModel):
    """Request model for echo endpoint"""
    data: Dict[str, Any] = Field(..., description="Data to echo back")


class WebSocketMessage(BaseModel):
    """WebSocket message model"""
    action: str = Field(..., description="Action to perform: subscribe or unsubscribe")
    type: str = Field(..., description="Subscription type: positions, orders, or free_runners")
    symbol: Optional[str] = Field(None, description="Optional symbol for subscription")


class PositionData(BaseModel):
    """Position data model"""
    conid: Optional[int] = None
    symbol: Optional[str] = None
    position: Optional[float] = None
    avgCost: Optional[float] = None
    avgPrice: Optional[float] = None
    currentPrice: Optional[float] = None
    marketValue: Optional[float] = None
    unrealizedPnl: Optional[float] = None
    realizedPnl: Optional[float] = None
    currency: Optional[str] = None
    secType: Optional[str] = None
    description: Optional[str] = None
    unrealizedPnlPct: Optional[float] = None
    dailyPnl: Optional[float] = None
    priceChange: Optional[float] = None
