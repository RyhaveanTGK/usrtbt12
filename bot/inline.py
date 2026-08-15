
import logging
from config import *
from tools import *

logger = logging.getLogger("inline")

async def _send_inline_result(client, message, index):
    try:
        # Get inline bot results
        results = await client.get_inline_bot_results(app.me.username, query="")

        if results.results:
            # Get the result ID at the requested index
            result_id = results.results[index].id

            # Send the inline result
            await client.send_inline_bot_result(
                message.chat_id,
                query_id=results.query_id,
                result_id=result_id
            )
        else:
            await message.reply("No inline results found.")
    except Exception as e:
        logger.warning(f"Inline result send failed: {e}")
        await message.reply("Something went wrong sending that.")


@ryhavean_cmd("me")
@retry()
async def inline_handler(event):
    client = event.client
    message = event
    await _send_inline_result(client, message, 0)


@ryhavean_cmd("set")
@retry()
async def inline_handler1(event):
    client = event.client
    message = event
    await _send_inline_result(client, message, 1)
