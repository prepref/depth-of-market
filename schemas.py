from pydantic import BaseModel, Field, constr
from typing import Optional
from datetime import datetime
from uuid import UUID

class InstrumentBase(BaseModel):
    ticker: constr(regex='^[A-Z]{2,10}$')
    name: str = Field(..., min_length=1, max_length=100)

class InstrumentCreate(InstrumentBase):
    pass

class InstrumentResponse(InstrumentBase):
    class Config:
        from_attributes = True

class UserBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    role: str = Field(..., regex='^(USER|ADMIN)$')

class UserCreate(UserBase):
    pass

class UserResponse(UserBase):
    id: UUID
    api_key: str
    created_at: datetime

    class Config:
        from_attributes = True 