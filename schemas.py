from pydantic import BaseModel, Field
from typing import Optional, List

# Core collections

class User(BaseModel):
    name: str = Field(..., description="Full name")
    email: Optional[str] = Field(None, description="Email address")
    phone: str = Field(..., description="Phone number")
    city: Optional[str] = Field(None)
    address: Optional[str] = Field(None)
    is_active: bool = True

class Product(BaseModel):
    title: str = Field(..., description="Product title")
    description: Optional[str] = None
    price: float = Field(..., ge=0, description="Price")
    category: str = Field(..., description="Product category")
    in_stock: bool = True
    image_url: Optional[str] = None

class OrderItem(BaseModel):
    product_id: str
    title: str
    price: float
    quantity: int = Field(..., ge=1)

class CustomerInfo(BaseModel):
    name: str
    phone: str
    city: str
    address: str

class Order(BaseModel):
    items: List[OrderItem]
    customer: CustomerInfo
    payment_method: str = Field("COD")
    status: str = Field("new")
    total: float
    currency: str = Field("SYP")
