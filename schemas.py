from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from uuid import UUID
from enum import Enum

class Direction(str, Enum):
    BUY = "buy"
    SELL = "sell"

class OrderStatus(str, Enum):
    ACTIVE = "active"
    FILLED = "filled"
    CANCELLED = "cancelled"

class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"

class NewUser(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

class User(BaseModel):
    id: UUID
    name: str
    role: UserRole
    created_at: datetime

    class Config:
        from_attributes = True

class InstrumentCreate(BaseModel):
    ticker: str = Field(..., min_length=2, max_length=10, pattern="^[A-Z]{2,10}$")
    name: str = Field(..., min_length=1, max_length=100)

class InstrumentResponse(BaseModel):
    ticker: str
    name: str
    created_at: datetime

    class Config:
        from_attributes = True

class Level(BaseModel):
    price: int
    qty: int

class L2OrderBook(BaseModel):
    ticker: str
    bids: List[Level]
    asks: List[Level]

class LimitOrderBody(BaseModel):
    ticker: str
    direction: Direction
    price: int = Field(..., gt=0)
    qty: int = Field(..., gt=0)

class MarketOrderBody(BaseModel):
    ticker: str
    direction: Direction
    qty: int = Field(..., gt=0)

class LimitOrder(BaseModel):
    id: UUID
    user_id: UUID
    ticker: str
    direction: Direction
    price: int
    qty: int
    filled_qty: int
    status: OrderStatus
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class MarketOrder(BaseModel):
    id: UUID
    user_id: UUID
    ticker: str
    direction: Direction
    qty: int
    filled_qty: int
    status: OrderStatus
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class CreateOrderResponse(BaseModel):
    order: LimitOrder | MarketOrder
    transactions: List[dict]

class Transaction(BaseModel):
    id: UUID
    ticker: str
    price: int
    qty: int
    created_at: datetime

    class Config:
        from_attributes = True

class Ok(BaseModel):
    success: bool = True

class ValidationError(BaseModel):
    loc: List[str]
    msg: str
    type: str

class HTTPValidationError(BaseModel):
    detail: List[ValidationError] 