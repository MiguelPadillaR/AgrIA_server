import random
from datetime import datetime, timedelta

def n_random_dates_between(date1: str, date2: str, n: int):
    """
    Generate n random dates between date1 and date2 (inclusive), formatted as yyyy-mm-dd.
    """
    start = datetime.strptime(date1, "%Y-%m-%d")
    end = datetime.strptime(date2, "%Y-%m-%d")
    delta = (end - start).days

    if delta < 0:
        raise ValueError("date2 must be after date1")

    dates = [
        (start + timedelta(days=random.randint(0, delta))).strftime("%Y-%m-%d")
        for _ in range(n)
    ]
    return dates

# Example:
# dates = n_random_dates_between("2024-01-01", "2024-12-31", 5)
# print(dates)
