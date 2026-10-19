from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def uid() -> str:
    return str(uuid4())


def require(row, message="Resource not found"):
    if row is None:
        raise HTTPException(404, message)
    return row
