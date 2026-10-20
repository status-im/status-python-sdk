from typing import Optional
import datetime, re

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


def camel_to_snake(name: str) -> str:
    """
    Used to make camel case Status Backend keys
    more Pythonic (snake case). Function is used
    when the entire raw data point is returned.

    Parameters:
        - `name` - camel case dictionary key

    Output:
        - snake case `name`
    """
    s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
    s2 = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1)
    return s2.lower()
