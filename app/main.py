"""
IBKR Strategy Builder Backend - Main Application
"""
import uvicorn
import asyncio
import logging
import warnings
import os
import time
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
from .services.order_tracking_service import order_tracking_service
from .services.handlers.lite_handlers import _cleanup_stale_alerts

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

async def wait_for_ibkr_ready(max_attempts: int = None, delay: int = 5) -> None:
    """
    Wait for IBKR/ibeam to be authenticated and ready before starting the application
    
    Args:
        max_attempts: Maximum number of attempts (default from env or 60 = 5 minutes)
        delay: Delay between attempts in seconds (default: 5)
    """
    # Allow configuration via environment variables
    if max_attempts is None:
        max_attempts = int(os.getenv('IBKR_STARTUP_TIMEOUT_SECONDS', '300')) // delay  # Default 5 minutes
    
    logger.info(f"⏳ Waiting for IBKR to be ready and authenticated... (timeout: {max_attempts * delay}s)")
    
    for attempt in range(max_attempts):
        try:
            # Test IBKR connectivity through the existing service
            logger.debug(f"IBKR readiness check attempt {attempt + 1}/{max_attempts}")
            
            # Use the existing health check method
            health_result = ibkr_service.check_health()
            
            if health_result:
                logger.debug("IBKR health check passed!")
                
                # Additional check: try to get accounts (indicates full authentication)
                try:
                    accounts_result = ibkr_service.get_accounts()
                    if accounts_result and hasattr(accounts_result, 'data') and accounts_result.data:
                        elapsed_time = (attempt + 1) * delay
                        logger.info(f"✅ IBKR is ready and authenticated! (took {elapsed_time}s, found {len(accounts_result.data)} accounts)")
                        return
                    else:
                        logger.debug("IBKR responding but no accounts found yet (might need 2FA)...")
                except Exception as e:
                    logger.debug(f"IBKR accounts check failed: {e}")
            else:
                logger.debug("IBKR health check failed")
                
        except Exception as e:
            logger.debug(f"IBKR connectivity check failed: {e}")
        
        # Log progress every 10 attempts (every ~50 seconds with default delay)
        if (attempt + 1) % 10 == 0:
            elapsed_time = (attempt + 1) * delay
            remaining_time = (max_attempts - attempt - 1) * delay
            logger.info(f"⏳ Still waiting for IBKR... ({elapsed_time}s elapsed, ~{remaining_time}s remaining)")
            logger.info("💡 If this is taking long, check if 2FA authentication is needed on your mobile device")
        
        await asyncio.sleep(delay)
    
    # If we get here, IBKR never became ready
    total_wait_time = max_attempts * delay
    error_msg = f"❌ IBKR failed to become ready within {total_wait_time} seconds ({max_attempts} attempts)"
    logger.error(error_msg)
    logger.error("🔧 Troubleshooting steps:")
    logger.error("   1. Check if ibeam container is running: docker ps")
    logger.error("   2. Check ibeam logs: docker logs <container_id>")
    logger.error("   3. Verify IBKR credentials in environment variables")
    logger.error("   4. Accept 2FA authentication on your mobile device")
    logger.error("   5. Check if IBKR gateway is accessible at http://localhost:5000")
    logger.error("   6. Increase timeout with IBKR_STARTUP_TIMEOUT_SECONDS env var")
    
    raise Exception(error_msg)

async def periodic_alert_cleanup():
    """Periodic task to clean up stale alerts"""
    while True:
        try:
            await asyncio.sleep(3600)  # Run every hour
            _cleanup_stale_alerts(hours_old=24)  # Clean alerts older than 24 hours
        except asyncio.CancelledError:
            logger.info("Alert cleanup task cancelled")
            break
        except Exception as e:
            logger.error(f"Error in periodic alert cleanup: {e}")
            await asyncio.sleep(3600)  # Continue after error

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan"""
    # Startup
    logger.info("🚀 Starting IBKR Strategy Builder Backend...")
    
    # STEP 1: Wait for IBKR to be ready before starting any services
    try:
        await wait_for_ibkr_ready()
    except Exception as e:
        logger.error(f"Failed to connect to IBKR: {e}")
        logger.error("Application startup aborted.")
        raise
    
    # STEP 2: Now that IBKR is ready, start all other services
    logger.info("🔧 IBKR ready! Starting application services...")
    
    # Initialize IBKR service and check health (should work now)
    try:
        logger.info("Performing final IBKR health check...")
        health_check = ibkr_service.check_health()
        accounts = ibkr_service.get_accounts()
        logger.info(f"✅ IBKR Health: {health_check}")
        logger.info(f"✅ IBKR Accounts: {len(accounts.data) if accounts and accounts.data else 0} found")
    except Exception as e:
        logger.warning(f"IBKR final check warning: {e}")
    
    # Initialize Telegram bot in background
    try:
        # Start bot in background task so it doesn't block startup
        asyncio.create_task(telegram_service.start_bot())
        logger.info("📱 Telegram bot startup initiated")
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
    
    # Start order tracking service
    try:
        asyncio.create_task(order_tracking_service.start())
        logger.info("Order tracking service startup initiated")
    except Exception as e:
        logger.error(f"Failed to start order tracking service: {e}")
    
    # Start periodic alert cleanup
    try:
        asyncio.create_task(periodic_alert_cleanup())
        logger.info("Periodic alert cleanup task initiated")
    except Exception as e:
        logger.error(f"Failed to start alert cleanup task: {e}")
    
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
    try:
        await order_tracking_service.stop()
        logger.info("Order tracking service stopped")
    except Exception as e:
        logger.error(f"Error stopping order tracking service: {e}")

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
