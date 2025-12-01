from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx
import os

app = FastAPI()
SERVICES = {
    "auth": os.getenv("AUTH_SERVICE_URL", "http://auth-service:8001"),
    "order": os.getenv("ORDER_SERVICE_URL", "http://order-service:8002"),
    "table": os.getenv("TABLE_SERVICE_URL", "http://table-service:8003"),
    "notification": os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service:8004"),
    "menu": os.getenv("MENU_SERVICE_URL", "http://menu-service:8005"),
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def route_requests(request: Request, call_next):
    path = request.url.path
    method = request.method
    if path.startswith("/auth"):
        service_url = SERVICES["auth"]
        target_path = path.replace("/auth", "", 1) or "/"
    elif path.startswith("/orders"):
        service_url = SERVICES["order"]
        target_path = path.replace("/orders", "", 1) or "/"
    elif path.startswith("/tables"):
        service_url = SERVICES["table"]
        target_path = path.replace("/tables", "", 1) or "/"
    elif path.startswith("/notifications"):
        service_url = SERVICES["notification"]
        target_path = path.replace("/notifications", "", 1) or "/"
    elif path.startswith("/menu"):
        service_url = SERVICES["menu"]
        target_path = path.replace("/menu", "", 1) or "/"
    else:
        return await call_next(request)
    async with httpx.AsyncClient() as client:
        target_url = f"{service_url}{target_path}?{request.url.query}"
        
        try:
            response = await client.request(
                method=method,
                url=target_url,
                headers=dict(request.headers),
                content=await request.body(),
                timeout=30.0
            )
            
            try:
                content = response.json()
            except Exception:
                content = response.text
            
            return JSONResponse(
                content=content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Service unavailable")

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "api-gateway"}