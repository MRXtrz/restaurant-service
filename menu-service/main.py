from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import json
import os

app = FastAPI()

class Dish(BaseModel):
    id: int
    name: str
    price: str
    description: str
    category: str
    available: bool = True

def load_menu():
    menu_path = os.path.join(os.path.dirname(__file__), "menu.json")
    try:
        with open(menu_path, "r", encoding="utf-8") as f:
            menu_data = json.load(f)
            return [Dish(**item) for item in menu_data]
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"Ошибка загрузки меню: {e}")
        return []

MENU_ITEMS = load_menu()

@app.get("/dishes")
async def get_menu():
    return [dish for dish in MENU_ITEMS if dish.available]

@app.get("/dishes/{dish_id}")
async def get_dish(dish_id: int):
    for dish in MENU_ITEMS:
        if dish.id == dish_id and dish.available:
            return dish
    raise HTTPException(status_code=404, detail="Dish not found")

@app.get("/categories/{category}")
async def get_dishes_by_category(category: str):
    return [dish for dish in MENU_ITEMS if dish.category == category and dish.available]

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "menu-service"}
