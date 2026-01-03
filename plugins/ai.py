import asyncio
from google import genai
from hydrogram import Client, filters, enums
from info import GEMINI_API_KEY

# ==========================================
# 🧠 AI CONFIGURATION (Stable 1.5 Flash 🚀)
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

    # 1. EXTRACT PROMPT (SMART & ROBUST)
    prompt = ""
    
    # Case A: Argument directly (/ask Hello)
    if len(message.command) > 1:
        prompt = message.text.split(None, 1)[1]
    
    # Case B: Reply to Message (Text OR Caption)
    elif message.reply_to_message:
        prompt = message.reply_to_message.text or message.reply_to_message.caption or ""

    # 2. VALIDATE PROMPT
    if not prompt.strip():
        return await message.reply(
            "🤖 **Gemini AI**\n\n"
            "**Error:** कुछ लिखो भाई!\n\n"
            "Usage:\n"
            "• `/ask Who is Iron Man?`\n"
            "• Reply to text with `/ask`"
        )

    # 3. PROCESSING
    status = await message.reply("🧠 Thinking...")
    await client.send_chat_action(message.chat.id, enums.ChatAction.TYPING)

    try:
        loop = asyncio.get_event_loop()
        
        # 🔥 SWITCHED BACK TO STABLE MODEL
        # 'gemini-1.5-flash' has High Rate Limits (Best for Bots)
        response = await loop.run_in_executor(
            None, 
            lambda: ai_client.models.generate_content(
                model='gemini-1.5-flash', 
                contents=prompt
            )
        )
        
        if not response.text:
            return await status.edit("❌ **Error:** Empty Response from AI.")

        answer = response.text

        # 4. SEND (Split Long Messages)
        if len(answer) > 4000:
            for i in range(0, len(answer), 4000):
                await message.reply(answer[i:i+4000], parse_mode=enums.ParseMode.MARKDOWN)
            await status.delete()
        else:
            await status.edit(answer, parse_mode=enums.ParseMode.MARKDOWN)

    except Exception as e:
        await status.edit(f"❌ **Error:** `{str(e)}`")

