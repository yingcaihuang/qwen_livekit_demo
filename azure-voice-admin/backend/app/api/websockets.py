"""WebSocket endpoints for real-time log streaming."""

from fastapi import WebSocket, WebSocketDisconnect

from app.services.log_broadcaster import get_log_broadcaster


async def ws_session_logs(websocket: WebSocket, session_id: str) -> None:
    """WebSocket endpoint for streaming session logs in real-time.

    On connection:
      1. Accept the WebSocket connection
      2. Subscribe to LogBroadcaster for the given session_id

    The LogBroadcaster handles pushing LogEntry JSON messages to subscribed clients.
    This endpoint keeps the connection alive by waiting for incoming messages
    (to detect client disconnect).

    On disconnect: unsubscribe from LogBroadcaster.
    """
    broadcaster = get_log_broadcaster()
    await websocket.accept()
    await broadcaster.subscribe(session_id, websocket)
    try:
        # Keep connection alive — wait for messages to detect disconnect
        while True:
            # receive_text will raise WebSocketDisconnect when client disconnects
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.unsubscribe(session_id, websocket)
