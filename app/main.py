"""
IBKR Strategy Builder Backend - Main Application
"""
import uvicorn
import asyncio
import logging
import warnings
import os
from urllib3.exceptions import InsecureRequestWarning
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import routers
from .routers import api_router, websocket_router
from .routers.penny_stock_monitor_router import router as penny_stock_router
from .services import ibkr_service, telegram_service
from .routers.internal_router import router as internal_router
from .services import penny_stock_watcher
from .services import penny_position_monitor

logger = logging.getLogger(__name__)

# Suppress noisy/unverified HTTPS warnings from urllib3 in local/test environments
warnings.simplefilter("ignore", InsecureRequestWarning)

# Filter to suppress known telegram polling noise during startup/shutdown
class _SuppressTelegramPollingWarning(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        if "Updater.start_polling() got an unexpected keyword argument 'read_timeout'" in msg:
            return False
        # suppress updater-not-running shutdown message which occurs during reloader lifecycle
        if "This Updater is not running!" in msg:
            return False
        return True

logging.getLogger('app.services.telegram_service').addFilter(_SuppressTelegramPollingWarning())

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan"""
    # Startup
    logger.info("Starting application...")
    
    # Initialize IBKR service and check health
    # print("Initializing IBKR service...")
    # print('\n#### check_health ####')
    # print(ibkr_service.check_health())

    # print('\n#### tickle ####')
    # print(ibkr_service.tickle().data)

    # print('\n#### get_accounts ####')
    # print(ibkr_service.get_accounts().data)
    
    # Initialize Telegram bot in background
    # print("\nInitializing Telegram bot...")
    try:
        # Start bot in background task so it doesn't block startup
        asyncio.create_task(telegram_service.start_bot())
        logger.info("Telegram bot startup initiated")
    except Exception as e:
        logger.error(f"Failed to start Telegram bot: {e}")

    # Start penny stock watcher
    try:
        asyncio.create_task(penny_stock_watcher.penny_stock_watcher.start())
        logger.info("Penny stock watcher startup initiated")
    except Exception as e:
        logger.error(f"Failed to start penny stock watcher: {e}")
    # Start penny position monitor
    try:
        asyncio.create_task(penny_position_monitor.penny_position_monitor.start())
        logger.info("Penny position monitor startup initiated")
    except Exception as e:
        logger.error(f"Failed to start penny position monitor: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down application...")
    try:
        await telegram_service.stop_bot()
        logger.info("Telegram bot stopped")
    except Exception as e:
        logger.error(f"Error stopping Telegram bot: {e}")
    try:
        await penny_stock_watcher.penny_stock_watcher.stop()
    except Exception as e:
        logger.error(f"Error stopping penny stock watcher: {e}")
    try:
        await penny_position_monitor.penny_position_monitor.stop()
    except Exception as e:
        logger.error(f"Error stopping penny position monitor: {e}")

# Initialize FastAPI app
app = FastAPI(
    title="IBKR Strategy Builder Backend",
    description="Backend API for IBKR trading strategy builder with real-time WebSocket support and Telegram integration",
    version="1.0.0",
    lifespan=lifespan
)

# Allow CORS from local frontend origins used in development.
# Adjust origins in production as needed for security.
app.add_middleware(
    CORSMiddleware,
    # For local development allow all origins so browser preflight
    # requests (OPTIONS) succeed. In production, replace with a
    # strict allowlist.
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(api_router)
app.include_router(websocket_router)
app.include_router(penny_stock_router)
app.include_router(internal_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
