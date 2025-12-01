from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import redis
import jwt
import uuid
import os
from datetime import datetime, timedelta
from urllib.parse import urlparse

app = FastAPI()
redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
parsed = urlparse(redis_url)
redis_client = redis.Redis(
    host=parsed.hostname or 'redis',
    port=parsed.port or 6379,
    decode_responses=True
)

SECRET_KEY = "tableCafe"

class UserSession(BaseModel):
    user_id: str
    table_id: int
    role: str
    user_name: str
    created_at: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: str

@app.post("/sessions")
async def create_session(table_id: int, user_name: str, role: str = "customer"):
    user_id = str(uuid.uuid4())
    session = UserSession(
        user_id=user_id,
        table_id=table_id,
        role=role,
        user_name=user_name,
        created_at=datetime.now().isoformat()
    )
    
    redis_client.setex(
        f"session:{user_id}",
        int(timedelta(hours=24).total_seconds()),
        session.model_dump_json()
    )
    redis_client.sadd(f"table:{table_id}:users", user_id)
    token_data = {
        "user_id": user_id,
        "table_id": table_id,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=24)
    }
    token = jwt.encode(token_data, SECRET_KEY, algorithm="HS256")
    
    return Token(access_token=token, token_type="bearer", user_id=user_id)

@app.get("/sessions/{user_id}")
async def get_session(user_id: str):
    session_data = redis_client.get(f"session:{user_id}")
    if not session_data:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return UserSession.model_validate_json(session_data)

@app.get("/tables/{table_id}/users")
async def get_table_users(table_id: int):
    user_ids = redis_client.smembers(f"table:{table_id}:users")
    users = []
    
    for user_id in user_ids:
        session_data = redis_client.get(f"session:{user_id}")
        if session_data:
            users.append(UserSession.model_validate_json(session_data))
    
    return users

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "auth-service"}