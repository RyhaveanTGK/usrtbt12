
import asyncio
import logging
from config import *
from tools import *

logger = logging.getLogger("purge")

@ryhavean_cmd("purge")
@retry()
async def purge(event):
    client = event.client
    message = event
    chunk = []
    async for msg in client.get_chat_history(
        message.chat_id,
        limit=message.id - message.reply_to_message.id + 1,
    ):
        if msg.id < message.reply_to_message.id:
            break
        chunk.append(msg.id)
        if len(chunk) >= 100:
            await client.delete_messages(message.chat.id, chunk)
            chunk.clear()
            await asyncio.sleep(1)

    if len(chunk) > 0:
        await client.delete_messages(message.chat.id, chunk)

@ryhavean_cmd("delall")
@retry()
async def delete_all_messages(event):
    client = event.client
    message = event
    try:
        await message.delete()
    except Exception as e:
        logger.debug(f"delall: deleting command message failed: {e}")
    target_user = message.reply_to_message.from_user
    if not target_user:
        return

    try:
        message_ids = []
        async for msg in client.search_messages(
            message.chat_id,
            from_user=target_user.id
        ):
            message_ids.append(msg.id)
            if len(message_ids) >= 100:
                try:
                    await client.delete_messages(message.chat.id, message_ids)
                    message_ids = []
                    await asyncio.sleep(0.5)
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
        
        if message_ids:
            await client.delete_messages(message.chat.id, message_ids)
            
    except Exception:
        pass

@ryhavean_cmd("del")
@retry()
async def delete_message(event):
    client = event.client
    message = event
    if message.reply_to_message:
        try:
            await client.delete_messages(
                message.chat.id, 
                [message.reply_to_message.id, message.id]
            )
        except Exception:
            pass
