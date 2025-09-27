"""Local simulation: call the FastAPI router handler directly to simulate a POST
without running the server. Prints response and the affected stored parent order(s).
"""
from app.routers.penny_stock_monitor_router import add_penny_orders
from app.services.penny_stock_monitor import penny_stock_monitor


def run():
    payload = {
        "orders": [
            {
                "ticker": "SIM",
                "minimum_variation": 0.01,
                "orders": [
                    {
                        "parent_order_id": "sim-parent-2",
                        "limit_sell": "sim-limit-2",
                        "stop_loss": "sim-stop-2",
                        "target_price": 3.75,
                        "stop_loss_price": 2.1,
                        "free_runner": True
                    }
                ]
            }
        ]
    }

    # The router function expects a Pydantic model instance; call with dict and let FastAPI model coercion
    # Simpler: call the underlying monitor directly through router helper by constructing model manually
    class Dummy:
        def __init__(self, d):
            self._d = d
        def model_dump(self):
            return self._d

    resp = add_penny_orders(Dummy(payload))
    print('Handler response:', resp)

    # Inspect stored order
    o = penny_stock_monitor.get_order('sim-parent-1')
    print('Stored parent order:', o)


if __name__ == '__main__':
    run()
