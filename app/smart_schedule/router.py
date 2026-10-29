from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user_id
from app.database import get_db
from app.smart_schedule.schemas import SmartScheduleRequest, SmartScheduleResponse
from app.smart_schedule.generator import ScheduleGenerator

router = APIRouter(
    prefix="/analytics",
    tags=["Smart Schedule"],
    dependencies=[Depends(get_current_user_id)]
)

@router.post("/smart-schedule", response_model=SmartScheduleResponse)
def generate_smart_schedule(
    request: SmartScheduleRequest,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    """
    Generates a smart weekly schedule by learning from user history
    and avoiding fixed commitments.
    """
    generator = ScheduleGenerator(db, user_id)
    return generator.generate(request)
