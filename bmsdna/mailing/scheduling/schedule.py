from datetime import datetime, time, timezone, timedelta
from abc import ABC, abstractmethod
from typing import Literal
from enum import Enum
from dateutil.relativedelta import relativedelta

INVALID_DAY_ACTIONS = Literal["forward", "backward"]


class Weekday(Enum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


WeeksDays_No_WE = [Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY, Weekday.THURSDAY, Weekday.FRIDAY]


class Schedule(ABC):
    def __init__(self, tz: timezone, start: datetime) -> None:
        super().__init__()
        self.tz = tz
        self.start = start.astimezone(tz) if start.tzinfo is None else start

    def is_due(self, last_exec: datetime | None, *, now: datetime | None = None) -> bool:
        now = now or datetime.now(tz=self.tz)
        if last_exec is not None and (now - last_exec).total_seconds() < 60 * 15:
            return False  # last execution was less than 15 minutes ago, that is not possible
        return self.calc_next_date(last_exec=last_exec, now=now) <= now

    @abstractmethod
    def calc_next_date(self, last_exec: datetime | None, *, now: datetime | None = None) -> datetime:
        pass

    @abstractmethod
    def calc_last_date(self, from_date: datetime) -> datetime:
        pass


class DeltaSchedule(Schedule):
    def __init__(
        self,
        tz: timezone,
        start: datetime,
        weekday: Weekday | list[Weekday] | None,
        day_time: time | None,
        td: timedelta | relativedelta,
        on_invalid_day_action: INVALID_DAY_ACTIONS = "forward",
    ) -> None:
        super().__init__(tz, start)
        self.weekdays = weekday
        self.day_time = (
            day_time
            if not day_time or day_time.tzinfo
            else time(hour=day_time.hour, minute=day_time.minute, second=day_time.second, tzinfo=tz)
        )
        self.weekdays_int = (
            [c.value for c in (weekday if isinstance(weekday, list) else [weekday])] if weekday else None
        )
        self.timedelta = td
        self.on_invalid_day_action = on_invalid_day_action

    def is_day_allowed(self, day: datetime) -> bool:
        if self.weekdays_int is None:
            return True
        return day.weekday() in self.weekdays_int

    def _real_start(self) -> datetime:
        real_start = self.start
        while not self.is_day_allowed(real_start):
            real_start = real_start + timedelta(days=1 if self.on_invalid_day_action == "forward" else -1)
        self.real_start = real_start
        return real_start

    def _next_date(self, dt: datetime) -> datetime:
        if self.day_time is not None:
            return (
                dt.replace(
                    hour=self.day_time.hour,
                    minute=self.day_time.minute,
                    second=self.day_time.second,
                    microsecond=self.day_time.microsecond,
                )
                + self.timedelta
            )
        return dt + self.timedelta

    def calc_last_date(self, from_date):
        if from_date < self.start:
            return self.start
        dt = from_date - self.timedelta
        while not self.is_day_allowed(dt):
            dt = dt - timedelta(days=-1)
        return dt

    def calc_next_date(self, last_exec: datetime | None, *, now: datetime | None = None) -> datetime:
        now = now or datetime.now(tz=self.tz)
        if now <= self._real_start() or last_exec is None:
            return self._real_start()
        if (now - last_exec).total_seconds() < 60 * 15:
            return last_exec + self.timedelta
        exec_date = self.start
        while exec_date < last_exec:
            exec_date = self._next_date(exec_date)
        if exec_date == last_exec:
            next_date = self._next_date(exec_date)
        else:
            next_date = exec_date
        next_date_orig = next_date
        while not self.is_day_allowed(next_date):
            next_date = next_date + timedelta(days=1 if self.on_invalid_day_action == "forward" else -1)
        if next_date <= last_exec:
            next_date = self._next_date(next_date_orig)
            while not self.is_day_allowed(next_date):
                next_date = next_date + timedelta(days=1 if self.on_invalid_day_action == "forward" else -1)

        if self.day_time:
            next_date = next_date.replace(
                hour=self.day_time.hour, minute=self.day_time.minute, second=self.day_time.second
            )
        return next_date
