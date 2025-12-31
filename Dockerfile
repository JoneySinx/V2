FROM python:3.11-slim

# ⚡ Environment optimizations
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /Auto-Filter-Bot

# 🧱 System deps (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 📦 Install python deps first (better cache)
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 🧠 🔥 HYDROGRAM BUG PATCH (ChannelForbidden.verified)
RUN python - << 'EOF'
import hydrogram.types.user_and_chats.chat as chat_mod

orig = chat_mod.Chat._parse_channel_chat

def safe_parse(client, channel):
    if not hasattr(channel, "verified"):
        channel.verified = False
    return orig(client, channel)

chat_mod.Chat._parse_channel_chat = safe_parse
print("✅ Hydrogram ChannelForbidden patch applied")
EOF

# 📂 Copy bot source
COPY . .

# 🚀 Start bot
CMD ["python", "bot.py"]
