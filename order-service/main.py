from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Optional
from enum import Enum
import redis
import json
import os
import asyncio
from datetime import datetime
from urllib.parse import urlparse

app = FastAPI()

redis_url = os.getenv("REDIS_URL", "redis://redis:6379")
parsed = urlparse(redis_url)
redis_client = redis.Redis(
    host=parsed.hostname or 'redis',
    port=parsed.port or 6379,
    decode_responses=True
)

class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    COMPLETED = "completed"
    PAID = "paid"

class CartItem(BaseModel):
    dish_id: int
    dish_name: str
    price: float
    quantity: int
    added_by: str

class PaymentInfo(BaseModel):
    user_id: str
    amount: float
    payment_method: str = "cash" 
    paid_at: str = datetime.now().isoformat()

class TableOrder(BaseModel):
    table_id: int
    cart: List[CartItem] = []
    status: OrderStatus = OrderStatus.PENDING
    created_at: str = datetime.now().isoformat()
    confirmed_by: Optional[str] = None
    paid_by: Optional[str] = None
    payment_info: Optional[PaymentInfo] = None
    total_amount: float = 0.0

@app.post("/tables/{table_id}/items")
async def add_to_cart(table_id: int, item: CartItem, background_tasks: BackgroundTasks):

    order_data = redis_client.get(f"order:table:{table_id}")
    if order_data:
        order = TableOrder.model_validate_json(order_data)
    else:
        order = TableOrder(table_id=table_id)
    existing_item = None
    for cart_item in order.cart:
        if cart_item.dish_id == item.dish_id and cart_item.added_by == item.added_by:
            existing_item = cart_item
            break
    
    if existing_item:
        existing_item.quantity += item.quantity
    else:
        order.cart.append(item)
    
    # Пересчитываем общую сумму
    order.total_amount = sum(item.price * item.quantity for item in order.cart)
    
    redis_client.setex(
        f"order:table:{table_id}",
        3600,
        order.model_dump_json()
    )
    
    background_tasks.add_task(notify_cart_update, table_id, order)
    
    return order

@app.get("/tables/{table_id}/order")
async def get_table_order(table_id: int):
    order_data = redis_client.get(f"order:table:{table_id}")
    if not order_data:
        return TableOrder(table_id=table_id)
    
    return TableOrder.model_validate_json(order_data)

@app.post("/tables/{table_id}/confirm")
async def confirm_order(table_id: int, user_id: str):
    order_data = redis_client.get(f"order:table:{table_id}")
    if not order_data:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order = TableOrder.model_validate_json(order_data)
    
    if not order.cart:
        raise HTTPException(status_code=400, detail="Cart is empty")
    
    order.status = OrderStatus.CONFIRMED
    order.confirmed_by = user_id
    order.total_amount = sum(item.price * item.quantity for item in order.cart)
    
    redis_client.setex(
        f"order:table:{table_id}",
        3600,
        order.model_dump_json()
    )
    
    await notify_order_confirmation(table_id, order)
    
    return order

@app.get("/tables/{table_id}/split-bill")
async def split_bill(table_id: int):
    order_data = redis_client.get(f"order:table:{table_id}")
    if not order_data:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order = TableOrder.model_validate_json(order_data)
    user_totals = {}
    
    for item in order.cart:
        if item.added_by not in user_totals:
            user_totals[item.added_by] = {
                "user_id": item.added_by,
                "items": [],
                "total": 0
            }
        
        item_total = item.price * item.quantity
        user_totals[item.added_by]["items"].append({
            "dish_name": item.dish_name,
            "quantity": item.quantity,
            "price": item.price,
            "total": item_total
        })
        user_totals[item.added_by]["total"] += item_total
    
    return list(user_totals.values())

@app.post("/tables/{table_id}/pay")
async def pay_order(table_id: int, user_id: str, payment_method: str = "cash"):
    """
    Оплатить заказ
    
    payment_method: cash, card, split
    """
    order_data = redis_client.get(f"order:table:{table_id}")
    if not order_data:
        raise HTTPException(status_code=404, detail="Order not found")
    
    order = TableOrder.model_validate_json(order_data)
    
    if order.status == OrderStatus.PENDING:
        raise HTTPException(status_code=400, detail="Order must be confirmed before payment")
    
    if order.status == OrderStatus.PAID:
        raise HTTPException(status_code=400, detail="Order already paid")
    
    # Вычисляем общую сумму
    total = sum(item.price * item.quantity for item in order.cart)
    
    # Создаем информацию об оплате
    payment_info = PaymentInfo(
        user_id=user_id,
        amount=total,
        payment_method=payment_method,
        paid_at=datetime.now().isoformat()
    )
    
    order.status = OrderStatus.PAID
    order.paid_by = user_id
    order.payment_info = payment_info
    order.total_amount = total
    
    # Сохраняем историю покупки
    purchase_history = {
        "table_id": table_id,
        "order": order.model_dump(),
        "paid_at": datetime.now().isoformat()
    }
    redis_client.lpush("purchases:history", json.dumps(purchase_history))
    redis_client.ltrim("purchases:history", 0, 999)  # Храним последние 1000 покупок
    
    redis_client.setex(
        f"order:table:{table_id}",
        3600,
        order.model_dump_json()
    )
    
    await notify_payment(table_id, order)
    
    return {
        "status": "paid",
        "order": order,
        "payment_info": payment_info
    }

@app.get("/tables/{table_id}/total")
async def get_order_total(table_id: int):
    """Получить общую сумму заказа"""
    order_data = redis_client.get(f"order:table:{table_id}")
    if not order_data:
        return {"table_id": table_id, "total": 0.0, "items_count": 0}
    
    order = TableOrder.model_validate_json(order_data)
    total = sum(item.price * item.quantity for item in order.cart)
    items_count = sum(item.quantity for item in order.cart)
    
    return {
        "table_id": table_id,
        "total": total,
        "items_count": items_count,
        "status": order.status
    }

@app.get("/purchases/history")
async def get_purchase_history(limit: int = 10):
    """Получить историю покупок"""
    history_data = redis_client.lrange("purchases:history", 0, limit - 1)
    purchases = []
    
    for item in history_data:
        try:
            purchases.append(json.loads(item))
        except:
            continue
    
    return {"purchases": purchases, "count": len(purchases)}

async def notify_cart_update(table_id: int, order: TableOrder):
    notification = {
        "type": "cart_updated",
        "table_id": table_id,
        "cart": [item.model_dump() for item in order.cart]
    }
    redis_client.publish(f"table:{table_id}", json.dumps(notification))

async def notify_order_confirmation(table_id: int, order: TableOrder):
    notification = {
        "type": "order_confirmed",
        "table_id": table_id,
        "order": order.model_dump()
    }
    redis_client.publish(f"table:{table_id}", json.dumps(notification))

async def notify_payment(table_id: int, order: TableOrder):
    notification = {
        "type": "order_paid",
        "table_id": table_id,
        "order": order.model_dump(),
        "payment_info": order.payment_info.model_dump() if order.payment_info else None
    }
    redis_client.publish(f"table:{table_id}", json.dumps(notification))

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "order-service"}