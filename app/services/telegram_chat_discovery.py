"""
Telegram chat ID discovery utility
"""
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

logger = logging.getLogger(__name__)

class TelegramChatDiscovery:
    """Utility to discover chat IDs for Telegram bot"""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.discovered_chats = {}
        self.application = None
    
    def setup_application(self):
        """Setup the application for chat discovery"""
        self.application = Application.builder().token(self.bot_token).build()
        
        # Add handlers
        start_handler = CommandHandler("start", self._start_command)
        message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        
        self.application.add_handler(start_handler)
        self.application.add_handler(message_handler)
        
        logger.info("Chat discovery application setup completed")
    
    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        chat = update.effective_chat
        
        # Store chat information
        self.discovered_chats[user.username or str(user.id)] = {
            "chat_id": str(chat.id),
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "chat_type": chat.type
        }
        
        logger.info(f"User {user.username} ({user.id}) started bot. Chat ID: {chat.id}")
        
        await update.message.reply_text(
            f"👋 Hello {user.first_name}!\n\n"
            f"🆔 Your Chat ID is: `{chat.id}`\n"
            f"👤 Username: @{user.username}\n\n"
            f"✅ Your chat has been registered for trading alerts!\n"
            f"You will now receive trading notifications with Buy/Sell buttons.",
            parse_mode='Markdown'
        )
    
    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular messages"""
        user = update.effective_user
        chat = update.effective_chat
        
        # Store chat information
        self.discovered_chats[user.username or str(user.id)] = {
            "chat_id": str(chat.id),
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "chat_type": chat.type
        }
        
        logger.info(f"Message from {user.username} ({user.id}). Chat ID: {chat.id}")
        
        await update.message.reply_text(
            f"📱 Message received!\n\n"
            f"🆔 Your Chat ID: `{chat.id}`\n"
            f"👤 Username: @{user.username}\n\n"
            f"✅ Chat registered for trading alerts!",
            parse_mode='Markdown'
        )
    
    def get_chat_id_for_username(self, username: str) -> str:
        """Get chat ID for a specific username"""
        user_info = self.discovered_chats.get(username)
        if user_info:
            return user_info["chat_id"]
        return None
    
    def get_all_discovered_chats(self) -> dict:
        """Get all discovered chats"""
        return self.discovered_chats.copy()
    
    async def run_discovery(self):
        """Run the chat discovery bot"""
        try:
            self.setup_application()
            logger.info("Starting chat discovery bot...")
            await self.application.run_polling()
        except Exception as e:
            logger.error(f"Error running chat discovery: {e}")

# Global instance
chat_discovery = TelegramChatDiscovery(bot_token="8331227211:AAHfYne1uCNrm58FoBHpsU8tD95ETepP_VY")
