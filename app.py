import time
from typing import Optional, List, Dict
from enum import Enum
from datetime import datetime, timedelta
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Depends, status, Header
from pydantic import BaseModel, Field, validator
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import os
from dotenv import load_dotenv
import logging
import json

from models import Base, User, Instrument, Order, Transaction, Balance
from routers import instruments
from database import get_db, engine, SessionLocal
from schemas import (
    NewUser, User as UserSchema, InstrumentResponse,
    L2OrderBook, Level, LimitOrderBody, MarketOrderBody,
    LimitOrder, MarketOrder, CreateOrderResponse, Transaction as TransactionSchema,
    Ok, Direction, OrderStatus, UserRole
)
from auth import get_current_user, get_current_admin_user

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Create database tables
Base.metadata.create_all(bind=engine)

# Create FastAPI app
app = FastAPI(
    title="Toy exchange",
    version="0.1.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(instruments.router)

def create_admin():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        api_key = f"{uuid.uuid4()}"
        cursor.execute(
            """
            INSERT INTO users (name, api_key, role)
            VALUES (%s, %s, %s)
            RETURNING id, name, role, api_key
            """,
            ("admin", api_key, UserRole.ADMIN.value)
        )
        conn.commit()
        
        return None
    
    except psycopg2.IntegrityError as e:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    finally:
        cursor.close()
        conn.close()

def get_db_connection():
    """Создает подключение к базе данных"""
    try:
        conn = psycopg2.connect(
            host="db",  # Используем имя сервиса из docker-compose
            port=5432,
            database=os.getenv("POSTGRES_DB", "trading"),
            user=os.getenv("POSTGRES_USER", "postgres"),
            password=os.getenv("POSTGRES_PASSWORD", "postgres")
        )
        return conn
    except Exception as e:
        logger.error(f"Error connecting to database: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database connection error"
        )

def get_db():
    """Dependency для получения сессии базы данных"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Models
class UserRole(str, Enum):
    USER = "USER"
    ADMIN = "ADMIN"

class Direction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"

class OrderStatus(str, Enum):
    NEW = "NEW"
    PARTIALLY_EXECUTED = "PARTIALLY_EXECUTED"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"
    SYSTEM_CANCELLED = "SYSTEM_CANCELLED"

class NewUser(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)

class User(BaseModel):
    id: uuid.UUID
    name: str
    role: UserRole
    api_key: str

class Instrument(BaseModel):
    ticker: str = Field(..., pattern=r'^[A-Z]{2,10}$')
    name: str = Field(..., max_length=100)

class Balance(BaseModel):
    user_id: uuid.UUID
    ticker: str
    amount: int = Field(..., ge=0)

class OrderCreate(BaseModel):
    direction: Direction
    ticker: str
    qty: int = Field(..., gt=0)
    price: Optional[int] = Field(None, gt=0)
    currency: str = Field(default="RUB", pattern=r'^[A-Z]{3}$')

class OrderBody(BaseModel):
    direction: Direction
    ticker: str
    qty: int
    price: int
    currency: str = Field(default="RUB", pattern=r'^[A-Z]{3}$')

class OrderResponse(BaseModel):
    id: uuid.UUID
    status: OrderStatus
    user_id: uuid.UUID
    body: OrderBody
    filled: int

class Transaction(BaseModel):
    id: uuid.UUID
    ticker: str
    price: int
    qty: int
    currency: str = Field(default="RUB", pattern=r'^[A-Z]{3}$')
    created_at: datetime

class Level(BaseModel):
    price: int
    qty: int

class L2OrderBook(BaseModel):
    bid_levels: List[Level]
    ask_levels: List[Level]

# Helpers
def get_current_user(Authorization: str = Header(...), db: Session = Depends(get_db)) -> UserSchema:
    if not Authorization.startswith("TOKEN "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header"
        )
    
    api_key = Authorization.removeprefix("TOKEN ")
    user = db.query(User).filter(User.api_key == api_key).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )
    
    return user

# Endpoints
@app.post("/api/v1/public/register", response_model=UserSchema, tags=["public"])
def register(user_data: NewUser, db: Session = Depends(get_db)):
    api_key = str(uuid.uuid4())
    db_user = User(
        name=user_data.name,
        api_key=api_key,
        role="USER"
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.get("/api/v1/public/instrument", response_model=List[InstrumentResponse], tags=["public"])
def list_instruments(db: Session = Depends(get_db)):
    return db.query(Instrument).all()

@app.get("/api/v1/public/orderbook/{ticker}", response_model=L2OrderBook, tags=["public"])
def get_orderbook(ticker: str, limit: int = 10, db: Session = Depends(get_db)):
    if limit > 25:
        limit = 25
    
    orders = db.query(Order).filter(
        Order.ticker == ticker,
        Order.status.in_([OrderStatus.NEW, OrderStatus.PARTIALLY_EXECUTED])
    ).order_by(
        Order.price.desc() if Order.direction == Direction.BUY else Order.price.asc()
    ).limit(limit * 2).all()
    
    bid_levels = []
    ask_levels = []
    
    for order in orders:
        level = Level(price=order.price, qty=order.qty - order.filled_qty)
        if order.direction == Direction.BUY:
            bid_levels.append(level)
        else:
            ask_levels.append(level)
    
    return L2OrderBook(bid_levels=bid_levels, ask_levels=ask_levels)

@app.get("/api/v1/public/transactions/{ticker}", response_model=List[TransactionSchema], tags=["public"])
def get_transaction_history(ticker: str, limit: int = 10, db: Session = Depends(get_db)):
    if limit > 100:
        limit = 100
    
    transactions = db.query(Transaction).filter(
        Transaction.ticker == ticker
    ).order_by(
        Transaction.created_at.desc()
    ).limit(limit).all()
    
    return [
        TransactionSchema(
            ticker=t.ticker,
            amount=t.qty,
            price=t.price,
            timestamp=t.created_at
        ) for t in transactions
    ]

@app.get("/api/v1/balance", response_model=Dict[str, int], tags=["balance"])
def get_balances(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    balances = db.query(Balance).filter(Balance.user_id == user.id).all()
    return {b.ticker: b.amount for b in balances}

@app.post("/api/v1/balance/deposit", response_model=Ok, tags=["balance"])
def deposit(ticker: str, amount: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Amount must be positive"
        )
    
    balance = db.query(Balance).filter(
        Balance.user_id == user.id,
        Balance.ticker == ticker
    ).first()
    
    if balance:
        balance.amount += amount
    else:
        balance = Balance(user_id=user.id, ticker=ticker, amount=amount)
        db.add(balance)
    
    db.commit()
    return Ok()

@app.post("/api/v1/balance/withdraw", response_model=Ok, tags=["balance"])
def withdraw(ticker: str, amount: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Amount must be positive"
        )
    
    balance = db.query(Balance).filter(
        Balance.user_id == user.id,
        Balance.ticker == ticker
    ).first()
    
    if not balance or balance.amount < amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient balance"
        )
    
    balance.amount -= amount
    db.commit()
    return Ok()

@app.post("/api/v1/order", response_model=CreateOrderResponse, tags=["order"])
def create_order(
    order: LimitOrderBody | MarketOrderBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Check if instrument exists
    instrument = db.query(Instrument).filter(Instrument.ticker == order.ticker).first()
    if not instrument:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ticker {order.ticker} not found"
        )
    
    # Check balance for sell orders
    if order.direction == Direction.SELL:
        balance = db.query(Balance).filter(
            Balance.user_id == user.id,
            Balance.ticker == order.ticker
        ).first()
        
        if not balance or balance.amount < order.qty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not enough balance to place sell order"
            )
    
    # Create order
    db_order = Order(
        user_id=user.id,
        ticker=order.ticker,
        direction=order.direction,
        order_type="LIMIT" if isinstance(order, LimitOrderBody) else "MARKET",
        price=order.price if isinstance(order, LimitOrderBody) else None,
        qty=order.qty,
        status=OrderStatus.NEW
    )
    
    db.add(db_order)
    db.commit()
    db.refresh(db_order)
    
    return CreateOrderResponse(order_id=db_order.id)

@app.get("/api/v1/order", response_model=List[LimitOrder | MarketOrder], tags=["order"])
def get_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    orders = db.query(Order).filter(Order.user_id == user.id).all()
    return [
        LimitOrder(
            id=o.id,
            status=o.status,
            user_id=o.user_id,
            body=LimitOrderBody(
                direction=o.direction,
                ticker=o.ticker,
                qty=o.qty,
                price=o.price
            ),
            filled=o.filled_qty
        ) if o.order_type == "LIMIT" else MarketOrder(
            id=o.id,
            status=o.status,
            user_id=o.user_id,
            body=MarketOrderBody(
                direction=o.direction,
                ticker=o.ticker,
                qty=o.qty
            )
        ) for o in orders
    ]

@app.get("/api/v1/order/{order_id}", response_model=LimitOrder | MarketOrder, tags=["order"])
def get_order(order_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.user_id == user.id
    ).first()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found"
        )
    
    if order.order_type == "LIMIT":
        return LimitOrder(
            id=order.id,
            status=order.status,
            user_id=order.user_id,
            body=LimitOrderBody(
                direction=order.direction,
                ticker=order.ticker,
                qty=order.qty,
                price=order.price
            ),
            filled=order.filled_qty
        )
    else:
        return MarketOrder(
            id=order.id,
            status=order.status,
            user_id=order.user_id,
            body=MarketOrderBody(
                direction=order.direction,
                ticker=order.ticker,
                qty=order.qty
            )
        )

@app.delete("/api/v1/order/{order_id}", response_model=Ok, tags=["order"])
def cancel_order(order_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    order = db.query(Order).filter(
        Order.id == order_id,
        Order.user_id == user.id,
        Order.status.in_([OrderStatus.NEW, OrderStatus.PARTIALLY_EXECUTED])
    ).first()
    
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order {order_id} not found or cannot be cancelled"
        )
    
    order.status = OrderStatus.CANCELLED
    db.commit()
    return Ok()

# Admin endpoints
@app.post("/api/v1/admin/instrument", response_model=Ok, tags=["admin"])
def add_instrument(instrument: InstrumentResponse, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    db_instrument = Instrument(**instrument.model_dump())
    db.add(db_instrument)
    try:
        db.commit()
        return Ok()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Instrument already exists"
        )

@app.delete("/api/v1/admin/instrument/{ticker}", response_model=Ok, tags=["admin"])
def delete_instrument(ticker: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    instrument = db.query(Instrument).filter(Instrument.ticker == ticker).first()
    if not instrument:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instrument {ticker} not found"
        )
    
    db.delete(instrument)
    db.commit()
    return Ok()

@app.get("/health")
async def health_check():
    return {"status": "ok"}

def main():
    create_admin()
     
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000
    )
    
if __name__ == "__main__":
    main()