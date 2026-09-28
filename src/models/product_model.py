from sqlmodel import SQLModel, Field
from enum import Enum

class ProductCategories(str, Enum):
    MOUSE = "mouse"
    KEYBOARD = "keyboard"
    MONITOR = "monitor"
    SALCHIPAPA = "salchipapa"

class Product(SQLModel, table=True):
    __tablename__ = "app_inv_products"

    id: int | None = Field(primary_key=True, default=None)
    name: str
    price: float
    category: ProductCategories
    quantity: int