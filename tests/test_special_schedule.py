from datetime import date, datetime, time, timedelta, timezone

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

    def calc_next_date(self, last_exec: datetime | None, *, now: datetime | None = None) -> datetime:
        now = now or datetime.now(tz=self.tz)
        if now.day < 11 and now.day not in (11, 18, 25):
            return super().calc_next_date(last_exec, now=now.replace(day=11))
        if now.day < 18 and now.day not in (11, 18, 25):
            return super().calc_next_date(last_exec, now=now.replace(day=18))
        if now.day < 25:
            return super().calc_next_date(last_exec, now=now.replace(day=25))
        return super().calc_next_date(last_exec, now=now)

    def _next_date(self, dt: datetime) -> datetime:
        assert self.day_time is not None
        if dt.day < 11:
            return dt.replace(
                day=11,
                hour=self.day_time.hour,
                minute=self.day_time.minute,
                second=self.day_time.second,
                microsecond=self.day_time.microsecond,
            )
        if dt.day < 18:
            return dt.replace(
                day=18,
                hour=self.day_time.hour,
                minute=self.day_time.minute,
                second=self.day_time.second,
                microsecond=self.day_time.microsecond,
            )
        if dt.day < 25:
            return dt.replace(
                day=25,
                hour=self.day_time.hour,
                minute=self.day_time.minute,
                second=self.day_time.second,
                microsecond=self.day_time.microsecond,
            )
        # after 25th, we send every day until end of month
        next_dt = (
            dt.replace(
                hour=self.day_time.hour,
                minute=self.day_time.minute,
                second=self.day_time.second,
                microsecond=self.day_time.microsecond,
            )
            + self.timedelta
        )
        # crossing into a new month resets to the 11th
        if next_dt.month != dt.month:
            return next_dt.replace(day=11)
        return next_dt

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
    # Tests should be sent at 11, 18, 25, 26, 27, 28 of each month, but not on weekends or holidays. The first send should be on Jan 30, 2026, and then every month on the same days.
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
    assert not s.is_due(datetime(2026, 1, 31, 7, 1, tzinfo=TZONE), now=datetime(2026, 2, 2, 7, 1, tzinfo=TZONE))
    assert not s.is_due(datetime(2026, 1, 31, 7, 1, tzinfo=TZONE), now=datetime(2026, 2, 3, 7, 1, tzinfo=TZONE))
    assert s.is_due(datetime(2026, 1, 31, 7, 1, tzinfo=TZONE), now=datetime(2026, 2, 11, 7, 1, tzinfo=TZONE))
    assert not s.is_due(datetime(2026, 2, 11, 7, 1, tzinfo=TZONE), now=datetime(2026, 2, 12, 7, 1, tzinfo=TZONE))
    assert not s.is_due(datetime(2026, 2, 11, 7, 1, tzinfo=TZONE), now=datetime(2026, 2, 13, 7, 1, tzinfo=TZONE))
    assert s.is_due(datetime(2026, 2, 11, 7, 1, tzinfo=TZONE), now=datetime(2026, 2, 18, 7, 1, tzinfo=TZONE))
    assert not s.is_due(datetime(2026, 2, 18, 7, 1, tzinfo=TZONE), now=datetime(2026, 2, 19, 7, 1, tzinfo=TZONE))
    assert s.is_due(datetime(2026, 2, 18, 7, 1, tzinfo=TZONE), now=datetime(2026, 2, 25, 7, 1, tzinfo=TZONE))
    assert s.is_due(datetime(2026, 2, 18, 7, 1, tzinfo=TZONE), now=datetime(2026, 2, 26, 7, 1, tzinfo=TZONE))
    assert s.is_due(datetime(2026, 2, 18, 7, 1, tzinfo=TZONE), now=datetime(2026, 2, 27, 7, 1, tzinfo=TZONE))
    assert s.is_due(datetime(2026, 2, 18, 7, 1, tzinfo=TZONE), now=datetime(2026, 2, 28, 7, 1, tzinfo=TZONE))


def test_sox_mail_weekends_and_holidays():
    # January 2026: 11th, 18th, 25th all fall on Sunday → each forwards to the following Monday
    @sox_schedule_mail(
        "compliance",
        "sox_mail_jan_we",
        day_time=time(6, 0, tzinfo=TZONE),
        start_date=datetime(2026, 1, 5, 6, 0, tzinfo=TZONE),  # Monday Jan 5
        retry_on_empty_send=False,
    )
    def _jan(info: GenerationInfo) -> None:
        pass

    s = _registry[("compliance", "sox_mail_jan_we")].schedule
    assert s is not None

    # Jan 11 = Sunday → not due; due on Mon Jan 12
    assert not s.is_due(datetime(2026, 1, 5, 7, 1, tzinfo=TZONE), now=datetime(2026, 1, 11, 7, 1, tzinfo=TZONE))
    assert s.is_due(datetime(2026, 1, 5, 7, 1, tzinfo=TZONE), now=datetime(2026, 1, 12, 7, 1, tzinfo=TZONE))
    # Jan 18 = Sunday → not due; due on Mon Jan 19
    assert not s.is_due(datetime(2026, 1, 12, 7, 1, tzinfo=TZONE), now=datetime(2026, 1, 18, 7, 1, tzinfo=TZONE))
    assert s.is_due(datetime(2026, 1, 12, 7, 1, tzinfo=TZONE), now=datetime(2026, 1, 19, 7, 1, tzinfo=TZONE))
    # Jan 25 = Sunday → not due; due on Mon Jan 26
    assert not s.is_due(datetime(2026, 1, 19, 7, 1, tzinfo=TZONE), now=datetime(2026, 1, 25, 7, 1, tzinfo=TZONE))
    assert s.is_due(datetime(2026, 1, 19, 7, 1, tzinfo=TZONE), now=datetime(2026, 1, 26, 7, 1, tzinfo=TZONE))

    # April 2026: 11th, 18th, 25th all fall on Saturday → each forwards past Sat+Sun to Monday
    @sox_schedule_mail(
        "compliance",
        "sox_mail_apr_we",
        day_time=time(6, 0, tzinfo=TZONE),
        start_date=datetime(2026, 4, 1, 6, 0, tzinfo=TZONE),  # Wednesday Apr 1
        retry_on_empty_send=False,
    )
    def _apr(info: GenerationInfo) -> None:
        pass

    s = _registry[("compliance", "sox_mail_apr_we")].schedule
    assert s is not None

    # Apr 11 = Sat, Apr 12 = Sun → not due either day; due Mon Apr 13
    assert not s.is_due(datetime(2026, 4, 1, 7, 1, tzinfo=TZONE), now=datetime(2026, 4, 11, 7, 1, tzinfo=TZONE))
    assert not s.is_due(datetime(2026, 4, 1, 7, 1, tzinfo=TZONE), now=datetime(2026, 4, 12, 7, 1, tzinfo=TZONE))
    assert s.is_due(datetime(2026, 4, 1, 7, 1, tzinfo=TZONE), now=datetime(2026, 4, 13, 7, 1, tzinfo=TZONE))
    # Apr 18 = Sat → not due; due Mon Apr 20
    assert not s.is_due(datetime(2026, 4, 13, 7, 1, tzinfo=TZONE), now=datetime(2026, 4, 18, 7, 1, tzinfo=TZONE))
    assert s.is_due(datetime(2026, 4, 13, 7, 1, tzinfo=TZONE), now=datetime(2026, 4, 20, 7, 1, tzinfo=TZONE))

    # December 2026: Dec 25 = Christmas (Friday, CH public holiday).
    # The registry also registers Dec 26–31 as extra project holidays.
    # We walk forward dynamically so the assertion is correct regardless of which holidays
    # are loaded (depends on the year the module was imported).
    @sox_schedule_mail(
        "compliance",
        "sox_mail_dec_hol",
        day_time=time(6, 0, tzinfo=TZONE),
        start_date=datetime(2026, 12, 4, 6, 0, tzinfo=TZONE),  # Friday Dec 4
        retry_on_empty_send=False,
    )
    def _dec(info: GenerationInfo) -> None:
        pass

    s = _registry[("compliance", "sox_mail_dec_hol")].schedule
    assert s is not None

    last = datetime(2026, 12, 18, 7, 1, tzinfo=TZONE)
    assert not s.is_due(last, now=datetime(2026, 12, 25, 7, 1, tzinfo=TZONE))  # Christmas itself

    # Find the first weekday after Christmas that is not a holiday
    first_allowed = date(2026, 12, 26)
    while first_allowed.weekday() >= 5 or first_allowed in HOLIDAYS:
        first_allowed += timedelta(days=1)
    assert s.is_due(last, now=datetime(first_allowed.year, first_allowed.month, first_allowed.day, 7, 1, tzinfo=TZONE))
