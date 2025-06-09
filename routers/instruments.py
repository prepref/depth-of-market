from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import uuid

from database import get_db
from models import Instrument, User
from schemas import InstrumentCreate, InstrumentResponse
from auth import get_current_admin_user

router = APIRouter(
    prefix="/api/v1/admin/instrument",
    tags=["admin"]
)

@router.post("/", response_model=InstrumentResponse)
def create_instrument(
    instrument: InstrumentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    try:
        db_instrument = Instrument(**instrument.model_dump())
        db.add(db_instrument)
        db.commit()
        db.refresh(db_instrument)
        return db_instrument
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.get("/", response_model=List[InstrumentResponse])
def get_instruments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    return db.query(Instrument).all()

@router.get("/{ticker}", response_model=InstrumentResponse)
def get_instrument(
    ticker: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    instrument = db.query(Instrument).filter(Instrument.ticker == ticker).first()
    if not instrument:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instrument with ticker {ticker} not found"
        )
    return instrument

@router.put("/{ticker}", response_model=InstrumentResponse)
def update_instrument(
    ticker: str,
    instrument: InstrumentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    db_instrument = db.query(Instrument).filter(Instrument.ticker == ticker).first()
    if not db_instrument:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instrument with ticker {ticker} not found"
        )
    
    try:
        for key, value in instrument.model_dump().items():
            setattr(db_instrument, key, value)
        db.commit()
        db.refresh(db_instrument)
        return db_instrument
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.delete("/{ticker}")
def delete_instrument(
    ticker: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    db_instrument = db.query(Instrument).filter(Instrument.ticker == ticker).first()
    if not db_instrument:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instrument with ticker {ticker} not found"
        )
    
    try:
        db.delete(db_instrument)
        db.commit()
        return {"success": True}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        ) 