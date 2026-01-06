class script(object):

    # ──────────────────────────
    # 👋 WELCOME & START
    # ──────────────────────────
    START_TXT = """<b>👋 Hey {},

I am a Powerful Auto Filter Bot with High Speed Streaming & AI Capabilities. ⚡

✅ <u>FEATURES:</u>
• 🎥 Auto Filter (Movies/Series)
• 🚀 Fast Download & Watch Online
• 🧠 AI Chat & Image Generation
• 🛡️ Premium Protected Content

Add me to your group and make me Admin! 🚀</b>"""

    # ──────────────────────────
    # 🚨 REQUIRED VARIABLES (Do Not Remove)
    # ──────────────────────────
    # यह info.py के लिए जरूरी है, इसे हटाने से बोट क्रैश होगा।
    WELCOME_TEXT = """👋 Hello {mention}, Welcome to {title} group! 💞"""
    
    # यह फाइल कैप्शन के लिए जरूरी है।
    FILE_CAPTION = """<i>{file_name}</i>

⚡ <b>Fast Download & Watch Online</b>"""

    # ──────────────────────────
    # 📝 LOGS TEMPLATES
    # ──────────────────────────
    NEW_GROUP_TXT = """#NewGroup
Title: {}
ID: <code>{}</code>
Username: {}
Members: <code>{}</code>"""

    NEW_USER_TXT = """#NewUser
Name: {}
ID: <code>{}</code>"""

    # ──────────────────────────
    # ℹ️ HELP & COMMANDS
    # ──────────────────────────
    HELP_TXT = """<b>🛠️ HELP MENU</b>

<b>🎬 Auto Filter:</b>
Just search for Movie/Series name in Group or PM.

<b>🧠 AI Features:</b>
• <code>/ask [query]</code> - Chat with Gemini AI
• <code>/draw [prompt]</code> - Generate AI Images

<b>⚙️ Settings & Premium:</b>
• <code>/settings</code> - Configure Group Settings
• <code>/plan</code> - View Premium Plans
• <code>/myplan</code> - Check Your Status"""

    ABOUT_TXT = """<b>🤖 ABOUT ME</b>

• <b>Server:</b> <a href="https://koyeb.com">Koyeb</a>
• <b>Language:</b> Python 3
• <b>Library:</b> Hydrogram
• <b>Database:</b> MongoDB

<b>⚡ Features:</b>
• Multi-DB Support (Primary/Cloud/Archive)
• AI Integration (Gemini/SDXL)
• Fast Streaming Server"""

    # ──────────────────────────
    # 💎 PREMIUM PLAN TEXT
    # ──────────────────────────
    PLAN_TXT = """<b>💎 PREMIUM PLANS</b>

Activate premium to unlock exclusive features:

• 🚫 <b>No Ads / Shortlinks</b>
• ⚡ <b>High-Speed Streaming</b>
• 🧠 <b>Unlimited AI Usage</b>
• 📂 <b>Direct File Access</b>

<b>Pricing:</b>
• INR 30 / Month
• INR 80 / 3 Months

<b>Contact Admin:</b> @YourAdminUsername"""

    # ──────────────────────────
    # ⚠️ MESSAGES
    # ──────────────────────────
    NOT_FILE_TXT = """<b>❌ File Not Found!</b>

👉 Check spelling correctly.
👉 Try searching with Year.
👉 Use /ask to verify name."""

