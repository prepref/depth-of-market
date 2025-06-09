from sqlalchemy import Column, String, Boolean, DateTime, UUID, BigInteger, ForeignKey, CheckConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    api_key = Column(String(50), unique=True, nullable=False)
    role = Column(String(10), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("role IN ('USER', 'ADMIN')", name="check_role_values"),
    )

class Instrument(Base):
    __tablename__ = "instruments"

    ticker = Column(String(10), primary_key=True)
    name = Column(String(100), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("ticker ~ '^[A-Z]{2,10}$'", name="check_ticker_format"),
    ) 