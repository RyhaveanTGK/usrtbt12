"""
Ryhavean Userbot - Security Module
Prevents unauthorized users from configuring bots via bot commands
"""

import logging
from config import *
from tools import *
from languages import get_user_lang, get_text

logger = logging.getLogger("userbot.security")


async def is_owner(client, user_id: int) -> bool:
    """Check if user is the bot owner"""
    return user_id == client.uid


async def is_authorized(client, user_id: int) -> bool:
    """Check if user is authorized (owner or sudoer)"""
    return user_id == client.uid or await sudoers_filter()(None, user_id)


@on_event(events.CallbackQuery())
async def security_callback_filter(event):
    client = event.client
    query = event
    """Filter malicious callback queries that try to setup bots"""
    try:
        if not await is_owner(client, query.from_user.id):
            # Prevent non-owners from executing setup-related callbacks
            restricted_keywords = ["setup", "addbot", "configure", "admin"]
            if any(keyword in query.data.lower() for keyword in restricted_keywords):
                await query.answer("❌ Unauthorized - Only owner can configure bots", show_alert=True)
                logger.warning(f"Blocked unauthorized setup attempt by {query.from_user.id}")
                return True
    except Exception as e:
        logger.error(f"Security callback filter error: {e}")
    
    return False


@ryhavean_cmd("setbot")
async def security_setbot_blocker(event):
    client = event.client
    message = event
    """Prevent any .setbot command from non-owners"""
    user_lang = await get_user_lang(message.from_user.id)
    
    if message.from_user.id != client.uid:
        error_msg = "❌ <b>Security Block</b>\n╰▸ Only account owner can configure bots"
        await edit_or_reply(message, error_msg)
        logger.warning(f"Blocked unauthorized .setbot attempt by {message.from_user.id}")
    else:
        # Owner is allowed - they can setup their own bot
        await edit_or_reply(message, "⚠️ <b>Warning</b>\n╰▸ Direct bot configuration is not recommended\n╰▸ Use environment variables instead (.env)")


@ryhavean_cmd(["addbot", "removebot", "botsetup"])
async def security_bot_commands_blocker(event):
    client = event.client
    message = event
    """Block bot management commands from being accessible"""
    user_lang = await get_user_lang(message.from_user.id)
    
    # Only allow owner
    if message.from_user.id != client.uid:
        error_msg = "❌ <b>Security</b>\n╰▸ Bot management is restricted to owner only"
        await edit_or_reply(message, error_msg)
        logger.warning(f"Blocked unauthorized bot command by {message.from_user.id}")
        return
    
    # Even if owner, suggest using .env instead
    await edit_or_reply(message, 
        "⚠️ <b>Security Notice</b>\n"
        "╰▸ Bot configuration via commands is disabled for security\n"
        "╰▸ Configure via .env file instead:\n"
        "• API_ID\n"
        "• API_HASH\n"
        "• SESSION_STR\n"
        "• BOT_TOKEN"
    )


@on_event(events.NewMessage(incoming=True, func=lambda e: e.is_private))
async def monitor_private_messages(event):
    client = event.client
    message = event
    """Monitor and log suspicious private messages"""
    try:
        # Check for setup/config keywords in private messages
        suspicious_keywords = ["setup", "addbot", "configure", "token", "session"]
        message_lower = message.text.lower() if message.text else ""
        
        if any(keyword in message_lower for keyword in suspicious_keywords):
            logger.info(f"Received setup-related message from {message.from_user.id}: {message_lower[:50]}")
            
            # Don't respond to avoid spam, but log it
            if "token" in message_lower or "session" in message_lower:
                logger.warning(f"Potential credential phishing attempt detected from {message.from_user.id}")
    
    except Exception as e:
        logger.debug(f"Private message monitoring error: {e}")


def create_security_middleware():
    """Create a security middleware for all commands"""
    
    async def security_check(client, message) -> bool:
        """
        Returns True if message should be blocked
        Returns False if message should be allowed
        """
        
        # Always allow owner
        if message.from_user.id == client.uid:
            return False
        
        # Block if trying to access bot setup commands
        if message.text:
            text_lower = message.text.lower()
            dangerous_commands = ["setbot", "addbot", "removebot", "botsetup"]
            
            for cmd in dangerous_commands:
                if text_lower.startswith(cmd):
                    logger.warning(f"Blocked dangerous command '{cmd}' from {message.from_user.id}")
                    return True
        
        return False
    
    return security_check


# Export security check for use in main
security_middleware = create_security_middleware()
