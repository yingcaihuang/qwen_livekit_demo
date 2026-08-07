"""
本地 HTTP 服务器 + Token API。
启动后访问 http://localhost:8090/test.html
"""

import http.server
import json
import os
import time

from dotenv import load_dotenv
from livekit.api import AccessToken, VideoGrants

load_dotenv()

PORT = 8090
os.chdir(os.path.dirname(os.path.abspath(__file__)))

API_KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/token":
            room_name = f"room-{int(time.time() * 1000)}"
            identity = "user1"

            token = (
                AccessToken(API_KEY, API_SECRET)
                .with_identity(identity)
                .with_grants(VideoGrants(room_join=True, room=room_name))
            )
            jwt_token = token.to_jwt()

            response = json.dumps(
                {
                    "token": jwt_token,
                    "room": room_name,
                    "identity": identity,
                }
            )

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(response.encode())
        else:
            super().do_GET()

    def log_message(self, format, *args):
        # 减少日志噪音，只打印非静态文件请求
        if "/api/" in str(args[0]):
            super().log_message(format, *args)


print(f"本地测试服务器启动: http://localhost:{PORT}/test.html")

with http.server.HTTPServer(("", PORT), Handler) as httpd:
    httpd.serve_forever()
