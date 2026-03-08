from fastapi import APIRouter, Depends, Query, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings
from app.smart_schedule.schemas import SmartScheduleRequest, SmartScheduleResponse
from app.smart_schedule.generator import ScheduleGenerator

def verify_api_key(x_api_key: str = Header(None)):
    if not x_api_key or x_api_key != settings.API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key")

router = APIRouter(
    prefix="/analytics",
    tags=["Smart Schedule"],
    dependencies=[Depends(verify_api_key)]
)

@router.post("/smart-schedule", response_model=SmartScheduleResponse)
def generate_smart_schedule(
    request: SmartScheduleRequest,
    user_id: int = Query(..., description="User ID"),
    db: Session = Depends(get_db),
):
    """
    Generates a smart weekly schedule by learning from user history
    and avoiding fixed commitments.
    """
    generator = ScheduleGenerator(db, user_id)
    return generator.generate(request)
