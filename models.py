from sqlalchemy import Column, String, Boolean, DateTime, UUID, BigInteger, ForeignKey, CheckConstraint, Enum as SQLEnum, PrimaryKeyConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from database import Base
from schemas import Direction, OrderStatus, UserRole

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    api_key = Column(String(50), unique=True, nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("role IN ('user', 'admin')", name="check_role_values"),
    )

class Instrument(Base):
    __tablename__ = "instruments"

    ticker = Column(String(10), primary_key=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("ticker ~ '^[A-Z]{2,10}$'", name="check_ticker_format"),
    )

class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    ticker = Column(String(10), ForeignKey("instruments.ticker"), nullable=False)
    direction = Column(SQLEnum(Direction), nullable=False)
    order_type = Column(String(10), nullable=False)
    price = Column(BigInteger, nullable=True)
    qty = Column(BigInteger, nullable=False)
    filled_qty = Column(BigInteger, default=0, nullable=False)
    status = Column(SQLEnum(OrderStatus), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    user = relationship("User", backref="orders")
    instrument = relationship("Instrument", backref="orders")

class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String(10), ForeignKey("instruments.ticker"), nullable=False)
    price = Column(BigInteger, nullable=False)
    qty = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    instrument = relationship("Instrument", backref="transactions")

class Balance(Base):
    __tablename__ = "balances"

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    ticker = Column(String(10), ForeignKey("instruments.ticker"), nullable=False)
    amount = Column(BigInteger, default=0, nullable=False)

    __table_args__ = (
        PrimaryKeyConstraint('user_id', 'ticker', name='balance_pk'),
        CheckConstraint("amount >= 0", name="check_positive_balance"),
    )

    user = relationship("User", backref="balances")
    instrument = relationship("Instrument", backref="balances") 