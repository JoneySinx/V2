from info import BIN_CHANNEL, URL
from utils import temp
import urllib.parse
import html
import logging

# Logger Setup
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 🎨 STREAMING TEMPLATE (Pro UI + MX Player)
# ─────────────────────────────────────────────
watch_tmplt = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{heading}</title>
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
    <link rel="stylesheet" href="https://cdn.plyr.io/3.7.8/plyr.css" />
    <style>
        :root {{
            --primary: #818cf8;
            --primary-hover: #6366f1;
            --bg-color: #0f172a;
            --player-bg: #1e293b;
            --text-main: #f8fafc;
            --text-sub: #94a3b8;
        }}
        
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        
        body {{
            font-family: 'Inter', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
        }}
        
        .header {{
            width: 100%;
            padding: 1.5rem;
            background: var(--player-bg);
            text-align: center;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            margin-bottom: 2rem;
        }}
        
        .file-title {{
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--primary);
            word-break: break-all;
            padding: 0 1rem;
        }}

        .player-wrapper {{
            width: 95%;
            max-width: 1000px;
            background: var(--player-bg);
            border-radius: 1rem;
            overflow: hidden;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
        }}

        .video-container {{
            position: relative;
            width: 100%;
        }}

        .controls-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 1rem;
            padding: 1.5rem;
        }}

        .btn {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            padding: 0.8rem;
            border-radius: 0.5rem;
            text-decoration: none;
            font-weight: 500;
            transition: all 0.2s;
            font-size: 0.9rem;
            border: 1px solid rgba(255,255,255,0.1);
            cursor: pointer;
        }}

        .btn-primary {{ background: var(--primary); color: white; border: none; }}
        .btn-primary:hover {{ background: var(--primary-hover); transform: translateY(-2px); }}
        
        .btn-secondary {{ background: rgba(255,255,255,0.05); color: var(--text-sub); }}
        .btn-secondary:hover {{ background: rgba(255,255,255,0.1); color: white; }}

        .footer {{
            margin-top: auto;
            padding: 2rem;
            color: var(--text-sub);
            font-size: 0.85rem;
            text-align: center;
        }}

        /* Toast Notification */
        #toast {{
            visibility: hidden;
            min-width: 250px;
            background-color: #333;
            color: #fff;
            text-align: center;
            border-radius: 8px;
            padding: 16px;
            position: fixed;
            z-index: 99;
            left: 50%;
            bottom: 30px;
            transform: translateX(-50%);
            font-size: 14px;
            box-shadow: 0 4px 10px rgba(0,0,0,0.3);
        }}
        #toast.show {{ visibility: visible; -webkit-animation: fadein 0.5s, fadeout 0.5s 2.5s; animation: fadein 0.5s, fadeout 0.5s 2.5s; }}
        
        @keyframes fadein {{ from {{bottom: 0; opacity: 0;}} to {{bottom: 30px; opacity: 1;}} }}
        @keyframes fadeout {{ from {{bottom: 30px; opacity: 1;}} to {{bottom: 0; opacity: 0;}} }}
    </style>
</head>
<body>

    <div class="header">
        <div class="file-title">{file_name}</div>
    </div>

    <div class="player-wrapper">
        <div class="video-container">
            <video id="player" playsinline controls>
                <source src="{src}" type="{mime_type}" />
            </video>
        </div>

        <div class="controls-grid">
            <a href="{src}" class="btn btn-primary">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                Download
            </a>
            
            <a href="vlc://{src}" class="btn btn-secondary">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                VLC Player
            </a>

            <a href="intent:{src}#Intent;package=com.mxtech.videoplayer.ad;S.title={file_name};end" class="btn btn-secondary">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 3l14 9-14 9V3z"></path></svg>
                MX Player
            </a>

            <button onclick="copyLink()" class="btn btn-secondary">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                Copy Link
            </button>
        </div>
    </div>

    <div class="footer">
        <p>⚠️ Video buffering? Use <b>VLC</b> or <b>MX Player</b> for smooth playback.</p>
        <p style="margin-top: 0.5rem; font-size: 0.75rem; opacity: 0.7;">Powered by Auto Filter Bot</p>
    </div>

    <div id="toast">Link Copied to Clipboard!</div>

    <script src="https://cdn.plyr.io/3.7.8/plyr.js"></script>
    <script>
        const player = new Plyr('#player', {{
            controls: ['play-large', 'play', 'progress', 'current-time', 'duration', 'mute', 'volume', 'settings', 'pip', 'fullscreen'],
            settings: ['speed']
        }});

        function copyLink() {{
            const el = document.createElement('textarea');
            el.value = "{src}";
            document.body.appendChild(el);
            el.select();
            document.execCommand('copy');
            document.body.removeChild(el);
            
            var x = document.getElementById("toast");
            x.className = "show";
            setTimeout(function(){{ x.className = x.className.replace("show", ""); }}, 3000);
        }}
    </script>
</body>
</html>
"""

async def media_watch(message_id):
    try:
        media_msg = await temp.BOT.get_messages(BIN_CHANNEL, message_id)
        media = getattr(media_msg, media_msg.media.value, None)
        
        if not media:
            return "<h2>❌ File Not Found or Deleted</h2>"

        # Generate Clean Stream Link
        src = urllib.parse.urljoin(URL, f'download/{message_id}')
        
        # Check MIME Type
        mime_type = getattr(media, 'mime_type', 'video/mp4')
        tag = mime_type.split('/')[0].strip()
        
        if tag == 'video':
            # Clean Data for Template
            file_name = html.escape(media.file_name if hasattr(media, 'file_name') else "Unknown Video")
            heading = f"Watch - {file_name}"
            
            # Fill Template safely
            return watch_tmplt.format(
                heading=heading,
                file_name=file_name,
                src=src,
                mime_type=mime_type
            )
        else:
            return f"""
            <div style="text-align:center; padding:50px; font-family:sans-serif;">
                <h1>⚠️ Not a Streamable Video</h1>
                <p>This file type ({mime_type}) cannot be played in browser.</p>
                <br>
                <a href="{src}" style="padding:10px 20px; background:#818cf8; color:white; text-decoration:none; border-radius:5px;">Click to Download</a>
            </div>
            """
    except Exception as e:
        logger.error(f"Render Template Error: {e}")
        return f"<h2>⚠️ Error: {str(e)}</h2>"

