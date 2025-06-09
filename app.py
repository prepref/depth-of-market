import time
from typing import Optional, List, Dict
from enum import Enum
from datetime import datetime
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor
from fastapi import FastAPI, HTTPException, Depends, status, Header
from pydantic import BaseModel, Field, validator
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

from .models import Base
from .routers import instruments

# Load environment variables
load_dotenv()

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db:5432/market")

# Create SQLAlchemy engine
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create FastAPI app
app = FastAPI(
    title="Market Depth API",
    description="API for market depth and trading operations",
    version="1.0.0"
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

# Database connection
def get_db_connection():
    conn = psycopg2.connect(
        dbname="storage_market",
        user="postgres",
        password="admin",
        host="localhost",
        port="5432",
        cursor_factory=RealDictCursor
    )
    return conn

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
def get_current_user(Authorization: str = Header(...)):
    if not Authorization.startswith("TOKEN "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header"
        )
    
    api_key = Authorization.removeprefix("TOKEN ")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT * FROM users WHERE api_key = %s",
            (api_key,)
        )
        user = cursor.fetchone()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key"
            )
        return user
    finally:
        cursor.close()
        conn.close()

# Endpoints
@app.post("/api/v1/public/register", response_model=User, tags=["public"])
def register(user_data: NewUser):
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
            (user_data.name, api_key, UserRole.USER.value)
        )
        user = cursor.fetchone()
        conn.commit()
        
        return {
            "id": str(user["id"]),
            "name": user["name"],
            "role": user["role"],
            "api_key": user["api_key"]
        }
    
    except psycopg2.IntegrityError as e:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/public/instrument", response_model=List[Instrument], tags=["public"])
def list_instruments(is_active: bool = True):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT name, ticker FROM instruments WHERE is_active = %s",
            (is_active,)
        )
        instruments = cursor.fetchall()
        return [{"name": item["name"], "ticker": item["ticker"]} for item in instruments]
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/balance", response_model=Dict[str, int], tags=["balance"])
def get_balances(user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT ticker, amount FROM balances WHERE user_id = %s",
            (user['id'],)
        )
        return {row['ticker']: row['amount'] for row in cursor.fetchall()}
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/order", tags=["order"])
def create_order(order: OrderCreate, user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT 1 FROM instruments WHERE ticker = %s LIMIT 1",
            (order.ticker,)
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ticker {order.ticker} not found"
            )

        if order.direction == Direction.SELL:
            cursor.execute(
                "SELECT amount FROM balances WHERE user_id = %s AND ticker = %s FOR UPDATE",
                (user["id"], order.ticker)
            )
            balance = cursor.fetchone()
            
            if not balance or balance["amount"] < order.qty:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Not enough balance to place sell order"
                )

        cursor.execute(
            """
            INSERT INTO orders 
            (user_id, ticker, direction, order_type, price, qty, status, currency)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (user["id"], order.ticker, order.direction.value, 
            OrderType.LIMIT.value if order.price else OrderType.MARKET.value, 
            order.price, order.qty, OrderStatus.NEW.value, order.currency)
        )
        new_order = cursor.fetchone()
        conn.commit()
        return {"success": True, "order_id": new_order["id"]}
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/order", response_model=List[OrderResponse], tags=["order"])
def get_orders(user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """
            SELECT * FROM orders WHERE user_id = %s
            """,
            (user["id"],)
        )
        users_orders = [
            {
                "id": order["id"],
                "status": order["status"],
                "user_id": order["user_id"],
                "body": {
                    "direction": order["direction"],
                    "ticker": order["ticker"],
                    "qty": order["qty"],
                    "price": order["price"],
                    "currency": order["currency"]
                },
                "filled": order["filled_qty"]
            }
            for order in cursor.fetchall()
            ]     
        return users_orders
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/order/{order_id}", response_model=OrderResponse, tags=["order"])
def get_order(order_id: uuid.UUID, user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """
            SELECT * FROM orders WHERE user_id = %s AND id = %s
            """,
            (user["id"], order_id)
        )
        order_data = cursor.fetchone()
        if not order_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Order {order_id} not found"
            )
            
        return {
            "id": order_data["id"],
            "status": order_data["status"],
            "user_id": order_data["user_id"],
            "body": {
                "direction": order_data["direction"],
                "ticker": order_data["ticker"],
                "qty": order_data["qty"],
                "price": order_data["price"],
                "currency": order_data["currency"]
            },
            "filled": order_data["filled_qty"]
        }
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/public/orderbook/{ticker}", response_model=L2OrderBook, tags=["public"])
def get_orderbook(ticker: str, limit: int = 10):
    if limit > 25:
        limit = 25
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """
            SELECT price, qty, side
            FROM orderbook
            WHERE ticker = %s
            ORDER BY 
                CASE WHEN side = 'BUY' THEN price END DESC,
                CASE WHEN side = 'SELL' THEN price END ASC
            LIMIT %s
            """,
            (ticker, limit * 2)
        )
        
        levels = cursor.fetchall()
        bid_levels = []
        ask_levels = []
        
        for level in levels:
            if level['side'] == 'BUY':
                bid_levels.append(Level(price=level['price'], qty=level['qty']))
            else:
                ask_levels.append(Level(price=level['price'], qty=level['qty']))
        
        return L2OrderBook(bid_levels=bid_levels, ask_levels=ask_levels)
    finally:
        cursor.close()
        conn.close()

@app.get("/api/v1/public/transactions/{ticker}", response_model=List[Transaction], tags=["public"])
def get_transaction_history(ticker: str, limit: int = 10):
    if limit > 100:
        limit = 100
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """
            SELECT id, ticker, price, qty, currency, created_at
            FROM transactions
            WHERE ticker = %s
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (ticker, limit)
        )
        
        transactions = cursor.fetchall()
        return [
            Transaction(
                id=row['id'],
                ticker=row['ticker'],
                price=row['price'],
                qty=row['qty'],
                currency=row['currency'],
                created_at=row['created_at']
            )
            for row in transactions
        ]
    finally:
        cursor.close()
        conn.close()

class DepositRequest(BaseModel):
    ticker: str = Field(..., pattern=r'^[A-Z]{2,10}$')
    amount: int = Field(..., gt=0)

@app.post("/api/v1/balance/deposit", tags=["balance"])
def deposit(deposit_data: DepositRequest, user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT 1 FROM instruments WHERE ticker = %s LIMIT 1", (deposit_data.ticker,))
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_NOT_FOUND,
                detail=f"Ticker {deposit_data.ticker} not found"
            )
        
        cursor.execute(
            """
            INSERT INTO balances (user_id, ticker, amount)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, ticker) 
            DO UPDATE SET amount = balances.amount + EXCLUDED.amount;
            """,
            (user["id"], deposit_data.ticker, deposit_data.amount)
        )

        conn.commit()

        return {
            "status": "success"
        }
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )
    finally:
        cursor.close()
        conn.close()

class WithdrawRequest(BaseModel):
    ticker: str = Field(..., pattern=r'^[A-Z]{2,10}$')
    amount: int = Field(..., gt=0)

@app.post("/api/v1/balance/withdraw", tags=["balance"])
def withdraw(withdraw_data: WithdrawRequest,user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "SELECT 1 FROM instruments WHERE ticker = %s",
            (withdraw_data.ticker,)
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Ticker {withdraw_data.ticker} not found"
            )

        cursor.execute(
            "SELECT amount FROM balances WHERE user_id = %s AND ticker = %s FOR UPDATE",
            (user["id"], withdraw_data.ticker)
        )
        balance = cursor.fetchone()
        
        if not balance:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No balance found for ticker {withdraw_data.ticker}"
            )
            
        if balance["amount"] < withdraw_data.amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient funds"
            )

        cursor.execute(
            """
            UPDATE balances 
            SET amount = amount - %s
            WHERE user_id = %s AND ticker = %s;
            """,
            (withdraw_data.amount, user["id"], withdraw_data.ticker)
        )
        
        conn.commit()
        
        return {
            "status": "success",
        }
    except psycopg2.Error as e:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )
    finally:
        cursor.close()
        conn.close()


# Admin endpoints
@app.post("/api/v1/admin/instrument", tags=["admin"])
def add_instrument(instrument: Instrument, user: dict = Depends(get_current_user)):
    if user['role'] != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """
            INSERT INTO instruments (ticker, name)
            VALUES (%s, %s)
            RETURNING *
            """,
            (instrument.ticker, instrument.name)
        )
        new_instrument = cursor.fetchone()
        conn.commit()
        return new_instrument
    except psycopg2.IntegrityError:
        conn.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Instrument already exists"
        )
    finally:
        cursor.close()
        conn.close()

class AdminDepositRequest(BaseModel):
    user_id: uuid.UUID
    ticker: str = Field(..., pattern=r'^[A-Z]{2,10}$')
    amount: int = Field(..., gt=0)

class AdminWithdrawRequest(BaseModel):
    user_id: uuid.UUID
    ticker: str = Field(..., pattern=r'^[A-Z]{2,10}$')
    amount: int = Field(..., gt=0)

class Ok(BaseModel):
    success: bool = True

@app.post("/api/v1/admin/balance/deposit", response_model=Ok, tags=["admin", "balance"])
def admin_deposit(request: AdminDepositRequest, user: dict = Depends(get_current_user)):
    if user["role"] != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin can deposit funds"
        )
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """
            INSERT INTO balances (user_id, ticker, amount)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, ticker)
            DO UPDATE SET amount = balances.amount + EXCLUDED.amount
            """,
            (request.user_id, request.ticker, request.amount)
        )
        conn.commit()
        return Ok()
    finally:
        cursor.close()
        conn.close()

@app.post("/api/v1/admin/balance/withdraw", response_model=Ok, tags=["admin", "balance"])
def admin_withdraw(request: AdminWithdrawRequest, user: dict = Depends(get_current_user)):
    if user["role"] != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin can withdraw funds"
        )
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            """
            UPDATE balances
            SET amount = amount - %s
            WHERE user_id = %s AND ticker = %s AND amount >= %s
            """,
            (request.amount, request.user_id, request.ticker, request.amount)
        )
        
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient balance or user not found"
            )
            
        conn.commit()
        return Ok()
    finally:
        cursor.close()
        conn.close()

@app.delete("/api/v1/admin/instrument/{ticker}", response_model=Ok, tags=["admin"])
def delete_instrument(ticker: str, user: dict = Depends(get_current_user)):
    if user["role"] != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin can delete instruments"
        )
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "DELETE FROM instruments WHERE ticker = %s",
            (ticker,)
        )
        
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Instrument {ticker} not found"
            )
            
        conn.commit()
        return Ok()
    finally:
        cursor.close()
        conn.close()

@app.delete("/api/v1/admin/user/{user_id}", response_model=User, tags=["admin", "user"])
def delete_user(user_id: uuid.UUID, user: dict = Depends(get_current_user)):
    if user["role"] != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin can delete users"
        )
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute(
            "DELETE FROM users WHERE id = %s RETURNING id, name, role, api_key",
            (user_id,)
        )
        
        deleted_user = cursor.fetchone()
        if not deleted_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )
            
        conn.commit()
        return {
            "id": str(deleted_user["id"]),
            "name": deleted_user["name"],
            "role": deleted_user["role"],
            "api_key": deleted_user["api_key"]
        }
    finally:
        cursor.close()
        conn.close()

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# Create database tables
Base.metadata.create_all(bind=engine)

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