"""
Pure helpers for deciding when scheduled automation rules should run.
Used by the APScheduler jobs in app/core/scheduler.py.
"""

from datetime import date, time

from app.models import AutomationRule, ScheduleFrequency


def should_run_scheduled(rule: AutomationRule, current_date: date, current_time: time) -> bool:
    """Determine if a scheduled rule should run now."""
    config = rule.trigger_config
    frequency = config.get("frequency", "daily")
    scheduled_time_str = config.get("time", "08:00")

    # Parse scheduled time
    try:
        hour, minute = map(int, scheduled_time_str.split(":"))
        scheduled_time = time(hour, minute)
    except (ValueError, AttributeError):
        scheduled_time = time(8, 0)

    # Check if within time window (1 hour window)
    time_diff = abs(
        (current_time.hour * 60 + current_time.minute)
        - (scheduled_time.hour * 60 + scheduled_time.minute)
    )
    if time_diff > 60:  # Not within 1 hour window
        return False

    if frequency == ScheduleFrequency.DAILY.value:
        return True

    elif frequency == ScheduleFrequency.WEEKLY.value:
        day_of_week = config.get("day_of_week", 0)  # 0 = Monday
        return current_date.weekday() == day_of_week

    elif frequency == ScheduleFrequency.BIWEEKLY.value:
        day_of_week = config.get("day_of_week", 0)
        if current_date.weekday() != day_of_week:
            return False
        # Check if it's an even or odd week based on rule creation
        week_number = current_date.isocalendar()[1]
        return week_number % 2 == 0

    elif frequency == ScheduleFrequency.MONTHLY.value:
        day_of_month = config.get("day_of_month", 1)
        return current_date.day == day_of_month

    return False
