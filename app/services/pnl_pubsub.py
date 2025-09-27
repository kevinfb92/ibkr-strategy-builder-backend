"""
Simple in-memory pub/sub for penny P/L websocket broadcasting.

This keeps a mapping of parent_order_id -> set of WebSocket connections
and provides async publish which will send JSON payloads to all
subscribed clients.

The module exposes a singleton `pnl_pubsub` for import/usage.
"""
import asyncio
import logging
from typing import Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class PnlPubSub:
    def __init__(self):
        # parent_order_id (str) -> set of WebSocket
        self._subs: Dict[str, Set[WebSocket]] = {}
        # simple lock for registry modifications
        self._lock = asyncio.Lock()

    async def publish(self, parent_order_id: str, payload: dict):
        """Send payload to all websockets subscribed to parent_order_id.

        This is async because send_json is an async operation.
        """
        if not parent_order_id:
            return
        async with self._lock:
            conns = list(self._subs.get(str(parent_order_id), set()))

        if not conns:
            return

        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception:
                logger.debug("Failed to send PnL payload to a websocket, removing it")
                # best-effort removal of dead websockets
                await self.unsubscribe(parent_order_id, ws)

    async def subscribe(self, parent_order_id: str, websocket: WebSocket):
        async with self._lock:
            key = str(parent_order_id)
            if key not in self._subs:
                self._subs[key] = set()
            self._subs[key].add(websocket)

    async def unsubscribe(self, parent_order_id: str, websocket: WebSocket):
        async with self._lock:
            key = str(parent_order_id)
            if key in self._subs:
                try:
                    self._subs[key].discard(websocket)
                except Exception:
                    pass
                if not self._subs[key]:
                    del self._subs[key]


# Singleton used by router and monitor
pnl_pubsub = PnlPubSub()
