"""
生成 LiveKit 房间 Token 的辅助脚本。
用法: python generate_token.py [room_name] [identity]
"""

import os
import sys

from dotenv import load_dotenv
from livekit.api import AccessToken, VideoGrants

load_dotenv()


def main():
    room = sys.argv[1] if len(sys.argv) > 1 else "test-room"
    identity = sys.argv[2] if len(sys.argv) > 2 else "user1"

    api_key = os.environ["LIVEKIT_API_KEY"]
    api_secret = os.environ["LIVEKIT_API_SECRET"]

    token = (
        AccessToken(api_key, api_secret)
        .with_identity(identity)
        .with_grants(VideoGrants(room_join=True, room=room))
    )

    jwt_token = token.to_jwt()
    print(f"Room:     {room}")
    print(f"Identity: {identity}")
    print(f"Token:    {jwt_token}")
    return jwt_token


if __name__ == "__main__":
    main()
