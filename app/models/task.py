"""
Task model — mirrors the Go backend's Task struct.
Table name: 'tasks' (GORM default pluralisation).
"""

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from app.database import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    name = Column(String, nullable=False)
    category = Column(String, nullable=False)          # deep-work, study, admin, gym, rest
    # DB types are TIME / DATE; app.database returns them as "HH:MM" / "YYYY-MM-DD" text.
    start_time = Column("start_time", String, nullable=False)  # "HH:MM" (end may be "24:00")
    end_time = Column("end_time", String, nullable=False)      # "HH:MM"
    status = Column(String, nullable=False, default="pending")  # pending, completed, skipped
    distractions = Column(Integer, nullable=False, default=0)
    energy = Column(Integer, nullable=False, default=3)         # 1–5
    date = Column(String, nullable=False, index=True)           # "YYYY-MM-DD"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    def duration_hours(self) -> float:
        """Calculate task duration in hours from start_time / end_time strings."""
        try:
            sh, sm = map(int, self.start_time.split(":"))
            eh, em = map(int, self.end_time.split(":"))
            return max(0, (eh * 60 + em - sh * 60 - sm) / 60)
        except (ValueError, AttributeError):
            return 0.0

    def __repr__(self):
        return f"<Task {self.id} '{self.name}' [{self.category}] {self.date}>"
