import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime

from database import db, create_document, get_documents
from schemas import Product as ProductSchema

app = FastAPI(title="Retail App API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------- Helpers ---------

def to_object_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid ID format")


def serialize_doc(doc: dict):
    if not doc:
        return None
    doc["id"] = str(doc.pop("_id"))
    # Convert datetimes to isoformat
    for k in ["created_at", "updated_at", "placed_at"]:
        if k in doc and isinstance(doc[k], datetime):
            doc[k] = doc[k].isoformat()
    return doc


def require_admin(admin_key: Optional[str]):
    expected = os.getenv("ADMIN_KEY", "admin123")
    if admin_key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized: invalid admin key")


# --------- Schemas ---------

class ProductCreate(BaseModel):
    title: str
    description: Optional[str] = None
    price: float = Field(..., ge=0)
    currency: str = Field("SYP", description="Currency code e.g., SYP")
    category: str
    image_url: Optional[str] = None
    in_stock: bool = True

class ProductUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = Field(None, ge=0)
    currency: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    in_stock: Optional[bool] = None

class CartItem(BaseModel):
    product_id: str
    title: str
    price: float
    quantity: int = Field(..., ge=1)

class CustomerInfo(BaseModel):
    name: str
    phone: str
    city: str
    address: str
    notes: Optional[str] = None

class OrderCreate(BaseModel):
    items: List[CartItem]
    customer: CustomerInfo
    payment_method: str = Field("COD", description="Cash on delivery only")

class OrderStatusUpdate(BaseModel):
    status: str = Field(..., description="new | confirmed | on_the_way | delivered | cancelled")
    tracking_note: Optional[str] = None

# --------- Basic Routes ---------

@app.get("/")
def root():
    return {"message": "Retail API شغال", "cod": True}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()
            response["database"] = "✅ Connected & Working"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response

# --------- Products ---------

@app.get("/api/products")
def list_products(q: Optional[str] = Query(None, description="search query"), category: Optional[str] = None):
    filt = {"in_stock": {"$ne": False}}
    if q:
        filt["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}},
            {"category": {"$regex": q, "$options": "i"}},
        ]
    if category:
        filt["category"] = category
    docs = get_documents("product", filt, limit=None)
    return [serialize_doc(d) for d in docs]

@app.get("/api/products/{product_id}")
def get_product(product_id: str):
    doc = db["product"].find_one({"_id": to_object_id(product_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")
    return serialize_doc(doc)

@app.post("/api/products")
def create_product(payload: ProductCreate, x_admin_key: Optional[str] = Header(None)):
    require_admin(x_admin_key)
    # Validate with ProductSchema then insert
    product = ProductSchema(
        title=payload.title,
        description=payload.description,
        price=payload.price,
        category=payload.category,
        in_stock=payload.in_stock,
    ).model_dump()
    # extra fields
    if payload.image_url:
        product["image_url"] = payload.image_url
    product["currency"] = payload.currency
    inserted_id = create_document("product", product)
    doc = db["product"].find_one({"_id": ObjectId(inserted_id)})
    return serialize_doc(doc)

@app.patch("/api/products/{product_id}")
def update_product(product_id: str, payload: ProductUpdate, x_admin_key: Optional[str] = Header(None)):
    require_admin(x_admin_key)
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if not updates:
        return {"updated": False}
    updates["updated_at"] = datetime.utcnow()
    res = db["product"].update_one({"_id": to_object_id(product_id)}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    doc = db["product"].find_one({"_id": to_object_id(product_id)})
    return serialize_doc(doc)

@app.delete("/api/products/{product_id}")
def delete_product(product_id: str, x_admin_key: Optional[str] = Header(None)):
    require_admin(x_admin_key)
    res = db["product"].delete_one({"_id": to_object_id(product_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"deleted": True}

# --------- Orders (COD) ---------

@app.post("/api/orders")
def create_order(payload: OrderCreate):
    if payload.payment_method != "COD":
        raise HTTPException(status_code=400, detail="Only COD is supported")
    if len(payload.items) == 0:
        raise HTTPException(status_code=400, detail="Cart is empty")

    total = sum(i.price * i.quantity for i in payload.items)
    order = {
        "items": [i.model_dump() for i in payload.items],
        "customer": payload.customer.model_dump(),
        "payment_method": "COD",
        "status": "new",
        "total": total,
        "currency": "SYP",
        "placed_at": datetime.utcnow(),
    }
    inserted_id = create_document("order", order)
    doc = db["order"].find_one({"_id": ObjectId(inserted_id)})
    return serialize_doc(doc)

@app.get("/api/orders")
def list_orders(x_admin_key: Optional[str] = Header(None), status: Optional[str] = None):
    require_admin(x_admin_key)
    filt = {}
    if status:
        filt["status"] = status
    docs = get_documents("order", filt)
    docs.sort(key=lambda d: d.get("placed_at", datetime.utcnow()), reverse=True)
    return [serialize_doc(d) for d in docs]

@app.get("/api/orders/{order_id}")
def get_order(order_id: str, x_admin_key: Optional[str] = Header(None)):
    require_admin(x_admin_key)
    doc = db["order"].find_one({"_id": to_object_id(order_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    return serialize_doc(doc)

@app.patch("/api/orders/{order_id}")
def update_order(order_id: str, payload: OrderStatusUpdate, x_admin_key: Optional[str] = Header(None)):
    require_admin(x_admin_key)
    updates = payload.model_dump(exclude_none=True)
    updates["updated_at"] = datetime.utcnow()
    res = db["order"].update_one({"_id": to_object_id(order_id)}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    doc = db["order"].find_one({"_id": to_object_id(order_id)})
    return serialize_doc(doc)

# Health
@app.get("/health")
def health():
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
