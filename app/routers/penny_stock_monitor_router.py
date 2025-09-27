from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from app.services.penny_stock_monitor import penny_stock_monitor

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
