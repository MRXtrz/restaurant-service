from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Dict, List
import redis
import json
import os
import asyncio
from urllib.parse import urlparse

app = FastAPI()

redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
parsed = urlparse(redis_url)
redis_client = redis.Redis(
    host=parsed.hostname or 'redis',
    port=parsed.port or 6379,
    decode_responses=True
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, table_id: int):
        await websocket.accept()
        if table_id not in self.active_connections:
            self.active_connections[table_id] = []
        self.active_connections[table_id].append(websocket)

    def disconnect(self, websocket: WebSocket, table_id: int):
        if table_id in self.active_connections:
            self.active_connections[table_id].remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast_to_table(self, message: str, table_id: int):
        if table_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[table_id]:
                try:
                    await connection.send_text(message)
                except Exception:
                    disconnected.append(connection)
            
            for connection in disconnected:
                self.active_connections[table_id].remove(connection)

manager = ConnectionManager()

@app.websocket("/ws/tables/{table_id}/users/{user_id}")
async def websocket_endpoint(websocket: WebSocket, table_id: int, user_id: str):
    await manager.connect(websocket, table_id)
    
    try:
        pubsub = redis_client.pubsub()
        pubsub.subscribe(f"table:{table_id}")
        
        async def listen_redis():
            while True:
                try:
                    message = pubsub.get_message(timeout=1.0)
                    if message and message['type'] == 'message':
                        await manager.broadcast_to_table(message['data'], table_id)
                    await asyncio.sleep(0.1)
                except Exception as e:
                    break
        
        listener_task = asyncio.create_task(listen_redis())
    
        try:
            while True:
                data = await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            listener_task.cancel()
            try:
                await listener_task
            except asyncio.CancelledError:
                pass
            pubsub.close()
            
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, table_id)

@app.get("/health")
async def health():
    return {"status": "healthy"}