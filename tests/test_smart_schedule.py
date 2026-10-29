import pytest
from app.smart_schedule.schemas import SmartScheduleRequest, Commitment, WeeklyGoals
from app.smart_schedule.generator import ScheduleGenerator

class MockTask:
    def __init__(self, category, start_time):
        self.category = category
        self.start_time = start_time
        self.date = "2026-03-01"
        self.status = "completed"

class MockQuery:
    def filter(self, *args, **kwargs): return self
    def order_by(self, *args, **kwargs): return self
    def all(self):
        return [
            MockTask("deep-work", "08:00"),
            MockTask("deep-work", "09:00"),
            MockTask("study", "15:00"),
            MockTask("rest", "20:00")
        ]

class MockDB:
    def query(self, *args, **kwargs): return MockQuery()

def test_history_learning():
    db = MockDB()
    generator = ScheduleGenerator(db, 1)
    generator.fetch_history(days_back=30)
    
    # 8+9 / 2 = 8
    assert 'deep-work' in generator._learned_patterns
    assert generator._learned_patterns['deep-work'] == 8
    assert generator._learned_patterns['study'] == 15

def test_generate_schedule():
    db = MockDB()
    generator = ScheduleGenerator(db, 1)
    
    req = SmartScheduleRequest(
        commitments=[
            Commitment(id="c1", name="Sleep", startTime="23:00", endTime="07:00", days=["Monday"])
        ],
        goals=WeeklyGoals(deepWorkHours=10, studyHours=5, restHours=7)
    )
    
    resp = generator.generate(req)
    
    # Check that Monday has blocks and no deep work happens during sleep 
    monday_blocks = [b for b in resp.blocks if b.day == "Monday"]
    assert len(monday_blocks) > 0
    
    # Daily DW goal is 10/5 = 2. Study is 5/5 = 1. Rest is 7/7 = 1. Fixed is 1 (Sleep)
    # Total on Monday = 2 + 1 + 1 + 1 = 5 blocks expected
    assert len(monday_blocks) == 5
    
    for b in monday_blocks:
        st = int(b.startTime.split(":")[0])
        # We prefer DW at 8. Sleep is 23 to 7. So 8 is free.
        if b.category == "deep-work":
            assert st >= 7 and st < 23 # Should not be during sleep hours
