from typing import Optional
import datetime

def to_datetime(value: Optional[int]) -> Optional[datetime.datetime]:
    """
    Convert Status Backend milliseconds to timestamps
    """
    if isinstance(value, type(None)):
        return None

    if value == 0:
        return None

    try:
        timestamp = datetime.datetime.fromtimestamp(value)
    except:
        timestamp = datetime.datetime.fromtimestamp(value / 1_000)

    return timestamp
