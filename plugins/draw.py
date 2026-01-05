import asyncio
import aiohttp
import io
import random
from hydrogram import Client, filters, enums
from hydrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from info import HF_TOKEN

# ==========================================
# 🎨 ULTRA ADVANCED IMAGE GENERATION
# Multi-Model Fallback System (Updated URL)
# ==========================================

# List of Models (If one fails, bot tries the next one)
MODELS = [
    "stabilityai/stable-diffusion-xl-base-1.0",    # Best Quality (SDXL)
    "prompthero/openjourney",                      # Midjourney Style
    "runwayml/stable-diffusion-v1-5",              # Fast & Reliable
    "CompVis/stable-diffusion-v1-4"                # Old but Gold
]

headers = {"Authorization": f"Bearer {HF_TOKEN}"}

async def query_hg(prompt, model_index=0):
    if model_index >= len(MODELS):
        return None, "All models failed."

    # 🔥 FIX: Changed URL from 'api-inference' to 'router'
    model_url = f"https://router.huggingface.co/models/{MODELS[model_index]}"
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(model_url, headers=headers, json={"inputs": prompt}, timeout=60) as response:
                if response.status == 200:
                    return await response.read(), MODELS[model_index]
                elif response.status == 503:
                    # Model Loading/Busy -> Wait & Retry same model once, then switch
                    await asyncio.sleep(3)
                    return await query_hg(prompt, model_index + 1)
                else:
                    # Other error (like 404 or Moved Permanently) -> Try next model
                    return await query_hg(prompt, model_index + 1)
        except Exception as e:
             print(f"Connection Error on {MODELS[model_index]}: {e}")
             return await query_hg(prompt, model_index + 1)

@Client.on_message(filters.command(["draw", "imagine", "img"]))
async def draw_image(client, message):
    # 1. Check Token
    if not HF_TOKEN:
        return await message.reply("❌ **Error:** Hugging Face Token (`HF_TOKEN`) is missing.")

    # 2. Extract Prompt
    prompt = ""
    if len(message.command) > 1:
        prompt = message.text.split(None, 1)[1]
    elif message.reply_to_message and message.reply_to_message.text:
        prompt = message.reply_to_message.text
    else:
        return await message.reply(
            "🎨 **AI Image Generator**\n\n"
            "Usage: `/draw <prompt>`\n"
            "Example: `/draw a cute cat in space, 4k`\n\n"
            "⚠️ **Note:** I create NEW images from text. I cannot edit existing photos yet."
        )

    # 3. Handle Photo Reply (Warn User)
    if message.reply_to_message and message.reply_to_message.photo:
        await message.reply(
            "⚠️ **Image Editing Not Supported**\n"
            "मैं पुरानी फोटो एडिट नहीं कर सकता। मैं आपके प्रॉम्प्ट से एक **नई फोटो** बना रहा हूँ।",
            quote=True
        )

    # 4. Enhance Prompt (Auto-Quality)
    if "quality" not in prompt.lower():
        prompt = f"{prompt}, cinematic lighting, 8k, highly detailed, realistic, masterpiece"

    status_msg = await message.reply(f"🎨 **Painting...**\n`{prompt}`\n\n_Trying multiple models..._")
    await client.send_chat_action(message.chat.id, enums.ChatAction.UPLOAD_PHOTO)

    try:
        # 5. Call API (Recursive Model Switcher)
        image_bytes, used_model = await query_hg(prompt)

        if not image_bytes:
            return await status_msg.edit("❌ **Error:** Server is too busy or API URL changed. Check logs.")

        # 6. Convert bytes & Send
        image_io = io.BytesIO(image_bytes)
        image_io.name = "art.jpg"

        await client.send_photo(
            chat_id=message.chat.id,
            photo=image_io,
            caption=f"✨ **Prompt:** `{prompt}`\n🎨 **Model:** `{used_model}`\n🤖 **Gen by:** @{client.me.username}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🗑 Delete", callback_data="close_data")]
            ])
        )
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit(f"❌ **Error:** `{str(e)}`")
