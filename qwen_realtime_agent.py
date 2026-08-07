"""
LiveKit Agent × Azure OpenAI Realtime (gpt-realtime-2.1)
========================================================

使用 Azure OpenAI 的 Realtime API，通过 LiveKit Agents 的 openai 插件对接。
本地自建 LiveKit Server 作为信令和媒体中转。

运行：
    python qwen_realtime_agent.py dev
"""

import logging
import os

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.plugins import openai, silero

load_dotenv()
logger = logging.getLogger("azure-realtime")


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "你是一个友好的中文语音助手，回答要简洁自然、口语化。"
                "遇到不确定的信息时要如实说明，不要编造。"
            )
        )


async def entrypoint(ctx: JobContext):
    await ctx.connect()

    realtime_llm = openai.realtime.RealtimeModel.with_azure(
        azure_deployment=os.environ["AZURE_DEPLOYMENT"],
        azure_endpoint=os.environ["AZURE_ENDPOINT"],
        api_key=os.environ["AZURE_API_KEY"],
        voice="alloy",
    )

    session = AgentSession(
        llm=realtime_llm,
        vad=silero.VAD.load(),
    )

    await session.start(agent=Assistant(), room=ctx.room)

    await session.generate_reply(instructions="用中文向用户问好，并简短介绍你能做什么。")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
