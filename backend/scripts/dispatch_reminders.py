"""Container Apps Job entrypoint — single dispatch pass then exit.

Usage:
    python -m scripts.dispatch_reminders
"""
import asyncio
import json
import logging
import sys

from app.database import SessionLocal
from app.services.reminders import dispatch


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


async def main() -> int:
    async with SessionLocal() as db:
        result = await dispatch(db)
    logger.info("reminders.dispatch_complete %s", json.dumps(result))
    # Return non-zero ONLY on catastrophic error; partial failures are normal.
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
