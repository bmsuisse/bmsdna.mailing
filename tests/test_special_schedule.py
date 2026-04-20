from datetime import datetime, time, timedelta, timezone

from bmsdna.mailing.registry import (
    HOLIDAYS,
    TZONE,
    DeltaSchedule,
    GenerationInfo,
    MailGenerationFunc,
    RegistryInfo,
    _registry,
)


class SOXTimer(DeltaSchedule):
    def __init__(self, tz: timezone, start: datetime, day_time: time) -> None:
        super().__init__(
            tz,
            start,
            weekday=None,
            day_time=day_time,
            td=timedelta(days=1),
            on_invalid_day_action="forward",
        )

    def _next_date(self, dt: datetime) -> datetime:
        assert self.day_time is not None
        if dt.day <= 11:
            return dt.replace(
                day=11,
                hour=self.day_time.hour,
                minute=self.day_time.minute,
                second=self.day_time.second,
                microsecond=self.day_time.microsecond,
            )
        if dt.day <= 18:
            return dt.replace(
                day=18,
                hour=self.day_time.hour,
                minute=self.day_time.minute,
                second=self.day_time.second,
                microsecond=self.day_time.microsecond,
            )
        if dt.day <= 25:
            return dt.replace(
                day=25,
                hour=self.day_time.hour,
                minute=self.day_time.minute,
                second=self.day_time.second,
                microsecond=self.day_time.microsecond,
            )
        # after 25th, we send every day until end of month
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

    def is_day_allowed(self, day: datetime) -> bool:
        if day.weekday() >= 5:
            return False
        if day in HOLIDAYS:
            return False
        return super().is_day_allowed(day)


def sox_schedule_mail(system: str, name: str, day_time: time, start_date: datetime, *, retry_on_empty_send: bool):
    def sox_decorator(func: MailGenerationFunc):
        _registry[(system, name)] = RegistryInfo(
            func,
            "sox_schedule",
            retry_on_empty_send=retry_on_empty_send,
            schedule=SOXTimer(TZONE, start_date, day_time),
        )
        return func

    return sox_decorator


def test_sox_mail():
    @sox_schedule_mail(
        "compliance",
        "sox_mail",
        day_time=time(6, 0, tzinfo=TZONE),
        start_date=datetime(2026, 1, 30, 6, 0, tzinfo=TZONE),
        retry_on_empty_send=False,
    )
    def _generate_mail(info: GenerationInfo) -> None:
        pass

    s = _registry[("compliance", "sox_mail")].schedule
    assert s is not None
    assert not s.is_due(None, now=datetime(2023, 8, 7, 5, 59, tzinfo=TZONE))
    assert s.is_due(None, now=datetime(2026, 1, 30, 7, 1, tzinfo=TZONE))
    assert not s.is_due(None, now=datetime(2026, 2, 2, 7, 1, tzinfo=TZONE))
    assert not s.is_due(None, now=datetime(2026, 2, 3, 7, 1, tzinfo=TZONE))
    assert s.is_due(None, now=datetime(2026, 2, 11, 7, 1, tzinfo=TZONE))
    assert not s.is_due(None, now=datetime(2026, 2, 12, 7, 1, tzinfo=TZONE))
    assert not s.is_due(None, now=datetime(2026, 2, 13, 7, 1, tzinfo=TZONE))
    assert s.is_due(None, now=datetime(2026, 2, 18, 7, 1, tzinfo=TZONE))
    assert not s.is_due(None, now=datetime(2026, 2, 19, 7, 1, tzinfo=TZONE))
    assert s.is_due(None, now=datetime(2026, 2, 25, 7, 1, tzinfo=TZONE))
    assert s.is_due(None, now=datetime(2026, 2, 26, 7, 1, tzinfo=TZONE))
    assert s.is_due(None, now=datetime(2026, 2, 27, 7, 1, tzinfo=TZONE))
    assert s.is_due(None, now=datetime(2026, 2, 28, 7, 1, tzinfo=TZONE))
