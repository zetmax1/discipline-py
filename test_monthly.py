from app.database import SessionLocal
from app.api.analytics_api import get_monthly_analytics
import asyncio

async def main():
    db = SessionLocal()
    try:
        res = await get_monthly_analytics(user_id=53, db=db)
        print("OK")
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        db.close()

asyncio.run(main())
