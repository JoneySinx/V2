# Credit - adarsh-goel

from aiohttp import web
from web.stream_routes import routes

# =========================================
# 🚀 WEB APP INITIALIZATION
# =========================================

# client_max_size=100MB set kiya hai taaki 'Payload Too Large' error na aaye
web_app = web.Application(client_max_size=100 * 1024 * 1024)

# Routes load karna
web_app.add_routes(routes)

