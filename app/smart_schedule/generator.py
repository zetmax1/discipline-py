import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.task import Task
from app.smart_schedule.schemas import SmartScheduleRequest, SmartScheduleResponse, ScheduleBlock, Commitment


class ScheduleGenerator:
    DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self._learned_patterns = {}

    def fetch_history(self, days_back: int = 30):
        # Calculate cutoff date
        cutoff = datetime.now() - timedelta(days=days_back)
        cutoff_str = cutoff.strftime('%Y-%m-%d')
        
        # Fetch tasks
        tasks = self.db.query(Task).filter(
            Task.user_id == self.user_id,
            Task.date >= cutoff_str,
            Task.status == 'completed'
        ).order_by(desc(Task.date)).all()
        
        # Analyze preferred times
        # Group by category -> List of start hours
        patterns = {'deep-work': [], 'study': [], 'rest': []}
        for t in tasks:
            if t.category in patterns and t.start_time:
                try:
                    hour = int(t.start_time.split(":")[0])
                    patterns[t.category].append(hour)
                except ValueError:
                    pass
        
        # Determine average preferred hour or default
        for cat, hours in patterns.items():
            if hours:
                # Mode or Average? Let's use simple average for now
                avg_hr = sum(hours) // len(hours)
                self._learned_patterns[cat] = avg_hr
            else:
                # Defaults if no history
                defaults = {'deep-work': 9, 'study': 14, 'rest': 19}
                self._learned_patterns[cat] = defaults.get(cat, 12)

    def _parse_time(self, time_str: str) -> int:
        """Helper to convert HH:MM to hours (e.g. 09:30 -> 9 or 9.5 if we want minutes, but let's stick to simple int hours for block overlap)"""
        return int(time_str.split(":")[0])

    def generate(self, request: SmartScheduleRequest) -> SmartScheduleResponse:
        self.fetch_history()
        reasoning = []
        blocks = []

        if len(self._learned_patterns) == 0:
            reasoning.append("No historical data found. Using default optimized schedule (Deep work mornings, Study afternoons).")
        else:
            reasoning.append("Learned your historical preferences to optimize placement.")

        # Per day requirements (simplified: goal / 5 weekdays)
        # In a real app, maybe spread across 7 days or rely on user settings
        daily_deep_work = max(1, int(request.goals.deepWorkHours // 5))
        daily_study = max(1, int(request.goals.studyHours // 5))
        daily_rest = max(1, int(request.goals.restHours // 7))

        preferred_dw = self._learned_patterns.get('deep-work', 9)
        preferred_st = self._learned_patterns.get('study', 14)
        
        reasoning.append(f"AI insight: Prioritizing deep work around {str(preferred_dw).zfill(2)}:00 based on your past focus peaks.")
        reasoning.append(f"AI insight: Study sessions generally placed around {str(preferred_st).zfill(2)}:00.")

        for di, day in enumerate(self.DAYS):
            # Find occupied hours for this day from fixed commitments
            day_commitments = [c for c in request.commitments if day in c.days]
            occupied_hours = set()
            
            for c in day_commitments:
                start_h = self._parse_time(c.startTime)
                end_h = self._parse_time(c.endTime)
                # Handle overnight sleepers (23:00 - 07:00)
                if start_h > end_h:
                    for h in range(start_h, 24): occupied_hours.add(h)
                    for h in range(0, end_h): occupied_hours.add(h)
                else:
                    for h in range(start_h, end_h): occupied_hours.add(h)
                
                blocks.append(ScheduleBlock(
                    id=str(uuid.uuid4()),
                    name=c.name,
                    category='fixed',
                    startTime=c.startTime,
                    endTime=c.endTime,
                    day=day
                ))

            # Helper to place block
            def place_block(hours_needed: int, preferred_start: int, name: str, cat: str):
                placed = 0
                search_radius = 0
                # expand search radius outward from preferred_start
                while placed < hours_needed and search_radius < 12:
                    for offset in [search_radius, -search_radius]:
                        h = (preferred_start + offset) % 24
                        # Dont schedule work between 22 and 6 unless preferred
                        if cat in ['deep-work', 'study'] and (h >= 22 or h < 6):
                            continue
                        
                        if h not in occupied_hours:
                            blocks.append(ScheduleBlock(
                                id=str(uuid.uuid4()),
                                name=name,
                                category=cat,
                                startTime=f"{str(h).zfill(2)}:00",
                                endTime=f"{str(h+1).zfill(2)}:00",
                                day=day
                            ))
                            occupied_hours.add(h)
                            placed += 1
                            if placed >= hours_needed: break
                    if search_radius > 0 == offset: # To avoid double processing offset 0
                        pass
                    if offset == search_radius: # Wait for both sides
                        search_radius += 1
                    else:
                        search_radius += 1

            # Only place heavy work on Weekdays mostly
            if di < 5:
                place_block(daily_deep_work, preferred_dw, "Deep Work", "deep-work")
                place_block(daily_study, preferred_st, "Study", "study")
            else:
                # Weekends lighter
                place_block(daily_study // 2, preferred_st, "Light Study / Review", "study")
                
            # Place rest every day
            place_block(daily_rest, self._learned_patterns.get('rest', 19), "Rest", "rest")

        return SmartScheduleResponse(blocks=blocks, reasoning=reasoning)
