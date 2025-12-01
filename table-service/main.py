from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Optional
import redis
import os
from urllib.parse import urlparse

app = FastAPI()

redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
parsed = urlparse(redis_url)
redis_client = redis.Redis(
    host=parsed.hostname or 'redis',
    port=parsed.port or 6379,
    decode_responses=True
)

class TableStatus(BaseModel):
    table_id: int
    status: str
    current_order: Optional[str] = None
    users: List[str] = []

@app.get("/tables")
async def get_all_tables():
    tables = []
    for i in range(1, 21):
        table_data = redis_client.get(f"table:{i}:status")
        if table_data:
            tables.append(TableStatus.model_validate_json(table_data))
        else:
            tables.append(TableStatus(table_id=i, status="free", users=[]))
    
    return tables

@app.get("/tables/{table_id}")
async def get_table_status(table_id: int):
    table_data = redis_client.get(f"table:{table_id}:status")
    if table_data:
        return TableStatus.model_validate_json(table_data)
    
    return TableStatus(table_id=table_id, status="free", users=[])

@app.post("/tables/{table_id}/join")
async def join_table(table_id: int, user_id: str):
    table_data = redis_client.get(f"table:{table_id}:status")
    if table_data:
        table = TableStatus.model_validate_json(table_data)
    else:
        table = TableStatus(table_id=table_id, status="occupied", users=[])
    
    if user_id not in table.users:
        table.users.append(user_id)
    
    redis_client.setex(
        f"table:{table_id}:status",
        3600,
        table.model_dump_json()
    )
    
    return table

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "table-service"}