import asyncio
from google import genai
from hydrogram import Client, filters, enums
from info import GEMINI_API_KEY

# ==========================================
# 🧠 AI CONFIGURATION (Gemini 3 Flash ⚡)
# ==========================================

if GEMINI_API_KEY:
    ai_client = genai.Client(api_key=GEMINI_API_KEY)
else:
    ai_client = None

# ==========================================
# 🗣️ AI CHAT COMMAND
# ==========================================

@Client.on_message(filters.command(["ask", "ai"]))
async def ask_ai(client, message):
    if not ai_client:
        return await message.reply("❌ **AI Error:** API Key missing.")

    if len(message.command) < 2 and not message.reply_to_message:
        return await message.reply(
            "⚡ **Gemini 3 Flash**\n\n"
            "Usage:\n"
            "• `/ask Who is Batman?`\n"
            "• Reply to text with `/ask`"
        )

    if len(message.command) > 1:
        question = message.text.split(None, 1)[1]
    elif message.reply_to_message and message.reply_to_message.text:
        question = message.reply_to_message.text
    else:
        return await message.reply("❌ कृपया सवाल पूछें।")

    status = await message.reply("⚡ Thinking (Flash Mode)...")
    await client.send_chat_action(message.chat.id, enums.ChatAction.TYPING)

    try:
        loop = asyncio.get_event_loop()
        
        # 🔥 USING LATEST GEMINI 3 FLASH MODEL
        response = await loop.run_in_executor(
            None, 
            lambda: ai_client.models.generate_content(
                model='gemini-3-flash-preview', 
                contents=question
            )
        )
        
        if not response.text:
            return await status.edit("❌ Empty Response.")

        answer = response.text

        if len(answer) > 4000:
            for i in range(0, len(answer), 4000):
                await message.reply(answer[i:i+4000], parse_mode=enums.ParseMode.MARKDOWN)
            await status.delete()
        else:
            await status.edit(answer, parse_mode=enums.ParseMode.MARKDOWN)

    except Exception as e:
        await status.edit(f"❌ **Error:** `{str(e)}`")

