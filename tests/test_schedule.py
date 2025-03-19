from datetime import datetime, time
from bmsdna.mailing.registry import (
    GenerationInfo,
    monthly_mail,
    TZONE,
    _registry,
    weekly_mail,
    monthly_mail_no_we,
    daily_mail,
)
from bmsdna.mailing.scheduling import Weekday


def test_monthly():
    @monthly_mail(
        "monthly",
        "test",
        datetime(2023, 8, 7, 6, 0, tzinfo=TZONE),
        day_time=time(6, 0, tzinfo=TZONE),
        on_invalid_day_action="backward",
        retry_on_empty_send=False,
    )
    def _generate_mail(info: GenerationInfo) -> None:
        pass

    s = _registry[("monthly", "test")].schedule
    assert s is not None
    assert not s.is_due(None, now=datetime(2023, 8, 7, 5, 59, tzinfo=TZONE))
    assert s.is_due(None, now=datetime(2023, 8, 7, 6, 1, tzinfo=TZONE))
    assert not s.is_due(datetime(2023, 8, 7, 6, tzinfo=TZONE), now=datetime(2023, 8, 7, 7, tzinfo=TZONE))
    assert s.is_due(datetime(2023, 8, 7, 7, tzinfo=TZONE), now=datetime(2023, 9, 7, 6, 1, tzinfo=TZONE))


def test_2weekly():
    @weekly_mail(
        "2weekly",
        "test",
        start_date=datetime(2023, 1, 1, 8, 0, tzinfo=TZONE),
        day=Weekday.SUNDAY,
        day_time=time(8, 0, tzinfo=TZONE),
        every_n_weeks=2,
        retry_on_empty_send=False,
    )
    def _generate_mail(info: GenerationInfo) -> None:
        pass

    s = _registry[("2weekly", "test")].schedule
    assert s is not None
    assert not s.is_due(None, now=datetime(2022, 12, 7, 5, 59, tzinfo=TZONE))
    assert s.is_due(None, now=datetime(2023, 1, 1, 8, 0, tzinfo=TZONE))
    assert s.is_due(None, now=datetime(2023, 1, 1, 8, 1, tzinfo=TZONE))
    assert not s.is_due(datetime(2023, 1, 1, 8, tzinfo=TZONE), now=datetime(2023, 1, 1, 8, tzinfo=TZONE))
    assert not s.is_due(datetime(2023, 1, 1, 8, tzinfo=TZONE), now=datetime(2023, 1, 1, 8, 1, tzinfo=TZONE))
    assert not s.is_due(datetime(2023, 1, 1, 8, tzinfo=TZONE), now=datetime(2023, 1, 1, 8, 20, tzinfo=TZONE))
    assert not s.is_due(datetime(2023, 1, 1, 8, tzinfo=TZONE), now=datetime(2023, 1, 8, 8, 1, tzinfo=TZONE))
    assert not s.is_due(datetime(2023, 1, 1, 8, tzinfo=TZONE), now=datetime(2023, 1, 13, 8, 1, tzinfo=TZONE))
    assert s.is_due(datetime(2023, 1, 1, 8, tzinfo=TZONE), now=datetime(2023, 1, 15, 8, 0, tzinfo=TZONE))
    assert s.is_due(datetime(2023, 1, 1, 8, tzinfo=TZONE), now=datetime(2023, 1, 15, 8, 1, tzinfo=TZONE))
    assert s.is_due(datetime(2023, 1, 1, 8, tzinfo=TZONE), now=datetime(2023, 1, 15, 8, 0, tzinfo=TZONE))
    assert s.is_due(datetime(2023, 1, 15, 8, tzinfo=TZONE), now=datetime(2023, 1, 29, 8, 0, tzinfo=TZONE))
    assert not s.is_due(datetime(2023, 1, 15, 8, tzinfo=TZONE), now=datetime(2023, 1, 28, 8, 0, tzinfo=TZONE))
    assert not s.is_due(datetime(2023, 1, 15, 8, tzinfo=TZONE), now=datetime(2023, 1, 28, 8, 1, tzinfo=TZONE))
    assert s.is_due(datetime(2023, 1, 15, 8, tzinfo=TZONE), now=datetime(2023, 1, 29, 8, 1, tzinfo=TZONE))


def test_monthly_no_we():
    @monthly_mail_no_we(
        "monthlynw",
        "test",
        start_date=datetime(2023, 1, 1, 8, 0, tzinfo=TZONE),
        day_of_month=1,
        day_time=time(8, 0, tzinfo=TZONE),
        on_invalid_day_action="backward",
        retry_on_empty_send=False,
    )
    def _generate_mail(info: GenerationInfo) -> None:
        pass

    s = _registry[("monthlynw", "test")].schedule
    assert s is not None
    assert s.is_due(None, now=datetime(2022, 12, 30, 8, 0, tzinfo=TZONE))  # 1.1 is a holiday, so is 31.12 -> 30.12
    assert not s.is_due(datetime(2022, 12, 30, 8, 0, tzinfo=TZONE), now=datetime(2023, 1, 1, 8, 0, tzinfo=TZONE))
    assert not s.is_due(datetime(2022, 12, 30, 8, 0, tzinfo=TZONE), now=datetime(2023, 1, 1, 8, 1, tzinfo=TZONE))
    assert not s.is_due(datetime(2022, 12, 30, 8, 0, tzinfo=TZONE), now=datetime(2023, 1, 1, 8, 20, tzinfo=TZONE))

    assert not s.is_due(datetime(2022, 12, 30, 8, 0, tzinfo=TZONE), now=datetime(2023, 1, 31, 8, 0, tzinfo=TZONE))
    assert s.is_due(datetime(2022, 12, 30, 8, 0, tzinfo=TZONE), now=datetime(2023, 2, 1, 8, 0, tzinfo=TZONE))
    assert s.is_due(datetime(2022, 12, 30, 8, 0, tzinfo=TZONE), now=datetime(2023, 2, 1, 8, 20, tzinfo=TZONE))
    assert not s.is_due(datetime(2023, 2, 1, 8, 20, tzinfo=TZONE), now=datetime(2023, 2, 28, 8, 1, tzinfo=TZONE))
    assert s.is_due(datetime(2023, 2, 1, 8, 20, tzinfo=TZONE), now=datetime(2023, 3, 1, 8, 1, tzinfo=TZONE))


def test_daily():
    @daily_mail(
        "daily_mailer",
        "test",
        day_time=time(6, 0, tzinfo=TZONE),
        start_date=datetime(2024, 3, 26, 6, 0, tzinfo=TZONE),
        retry_on_empty_send=False,
    )
    def _generate_mail(info: GenerationInfo) -> None:
        pass

    s = _registry[("daily_mailer", "test")].schedule
    assert s is not None
    assert s.is_due(None, now=datetime(2024, 3, 26, 6, 0, tzinfo=TZONE))
    assert not s.is_due(datetime(2024, 3, 26, 6, 0, tzinfo=TZONE), now=datetime(2024, 3, 26, 7, 0, tzinfo=TZONE))
    assert not s.is_due(datetime(2024, 3, 26, 7, 0, tzinfo=TZONE), now=datetime(2024, 3, 26, 10, 0, tzinfo=TZONE))
    assert s.is_due(datetime(2024, 3, 26, 7, 0, tzinfo=TZONE), now=datetime(2024, 3, 27, 10, 0, tzinfo=TZONE))
    assert s.calc_next_date(datetime(2024, 3, 26, 7, 12, tzinfo=TZONE)) == datetime(2024, 3, 27, 6, 0, tzinfo=TZONE)
