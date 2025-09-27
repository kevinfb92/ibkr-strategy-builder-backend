"""
IBKR Strategy Builder Backend - Main Application
"""
import uvicorn
from fastapi import FastAPI

# Import routers
from .routers import api_router, websocket_router
from .services import ibkr_service

# Initialize IBKR service and check health
print("Initializing IBKR service...")
print('\n#### check_health ####')
print(ibkr_service.check_health())

print('\n#### tickle ####')
print(ibkr_service.tickle().data)

print('\n#### get_accounts ####')
print(ibkr_service.get_accounts().data)

# Initialize FastAPI app
app = FastAPI(
    title="IBKR Strategy Builder Backend",
    description="Backend API for IBKR trading strategy builder with real-time WebSocket support",
    version="1.0.0"
)

# Include routers
app.include_router(api_router)
app.include_router(websocket_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
