import json
from app.routers.internal_router import penny_watcher_status

print(json.dumps(penny_watcher_status(), indent=2))
