from dataclasses import dataclass
from uuid import uuid4

from bmsdna.mailing.config import DEFAULT_SENDER, DEFAULT_SENDER_NAME
from .scheduling.schedule import Weekday, Schedule, DeltaSchedule, INVALID_DAY_ACTIONS
import pytz
from datetime import date, datetime, timezone, time
from typing import (
    Any,
    AsyncIterable,
    Awaitable,
    Final,
    Callable,
    Iterable,
    Literal,
    NamedTuple,
    Optional,
    TypedDict,
    Union,
    cast,
)
from datetime import timedelta
from .generation_context import GenerationContext
from dateutil.relativedelta import relativedelta
import holidays
import inspect
import time as time_module
from .message import BaseAttachment, MailMessage
import logging 

logger = logging.getLogger(__name__)

TZONE: Final[timezone] = pytz.timezone("Europe/Zurich")  # type: ignore
HOLIDAYS = holidays.country_holidays("CH")
year = datetime.now().year
for year in range(year, year + 3):  # holidays from 26 on
    HOLIDAYS.append(date(year, 12, 26))
    HOLIDAYS.append(date(year, 12, 27))
    HOLIDAYS.append(date(year, 12, 28))
    HOLIDAYS.append(date(year, 12, 29))
    HOLIDAYS.append(date(year, 12, 30))
    HOLIDAYS.append(date(year, 12, 31))


@dataclass(frozen=True)
class GenerationInfo:
    system: str
    mail_name: str
    dry_run: bool
    context: GenerationContext

    def make_mail(
        self,
        *,
        subject: str,
        entity_id: str,  # a unique id for the mail
        body: str,
        body_is_html: bool,
        to: Union[list[str], str],
        sender: str | None = DEFAULT_SENDER,
        sender_name: str | None = DEFAULT_SENDER_NAME,
        cc: Union[list[str], str, None] = None,
        bcc: Union[list[str], str, None] = None,
        attachments: "Union[list[BaseAttachment], None]" = None,
        importance: Optional[Literal["High", "normal", "low"]] = "normal",
        extra_infos: dict[str, Any] | None = None,
        send_method: Optional[Literal["SENDGRID"]] = None,
        error_receiver: Optional[str] = None,
    ) -> MailMessage:
        return MailMessage(
            entity=self.mail_name,
            entity_id=entity_id,
            system=self.system,
            subject=subject,
            body=body,
            body_is_html=body_is_html,
            to=to,
            sender=sender,
            sender_name=sender_name,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
            importance=importance,
            extra_infos=extra_infos,
            send_method=send_method,
            error_receiver=error_receiver,
        )


MailGenerationFunc = Callable[
    [GenerationInfo],
    MailMessage
    | Iterable[MailMessage]
    | None
    | Awaitable[MailMessage | Iterable[MailMessage] | None]
    | AsyncIterable[MailMessage],
]


@dataclass(frozen=True)
class RegistryInfo:
    func: MailGenerationFunc
    schedule_str: str
    retry_on_empty_send: bool
    schedule: Schedule | None


_registry: dict[tuple[str, str], RegistryInfo] = {}


_todos: list[tuple[str, str]] = []


def _get_send_mail_for_scheduler_fn(func: MailGenerationFunc, inf: tuple[str, str]):
    def todos():
        global _todos
        _todos.append(inf)

    return todos


def daily_mail(system: str, name: str, day_time: time, start_date: datetime, *, retry_on_empty_send: bool):
    def daily_decorator(func: MailGenerationFunc):
        _registry[(system, name)] = RegistryInfo(
            func,
            "daily",
            retry_on_empty_send=retry_on_empty_send,
            schedule=DailyTimerNoWe(TZONE, start_date, day_time),
        )
        return func

    return daily_decorator


def monthly_mail(
    system: str,
    name: str,
    start_date: datetime,
    day_time: time | None = None,
    every_n_months=1,
    *,
    on_invalid_day_action: INVALID_DAY_ACTIONS = "forward",
    retry_on_empty_send: bool,
):
    def monthly_decorator(func: MailGenerationFunc):
        _registry[(system, name)] = RegistryInfo(
            func,
            "monthly",
            retry_on_empty_send=retry_on_empty_send,
            schedule=DeltaSchedule(
                TZONE,
                start_date,
                None,
                day_time,
                relativedelta(months=every_n_months),
                on_invalid_day_action=on_invalid_day_action,
            ),
        )
        return func

    return monthly_decorator


def weekly_mail(
    system: str,
    name: str,
    day: Weekday,
    start_date: datetime,
    day_time: time | None = None,
    *,
    every_n_weeks=1,
    retry_on_empty_send: bool,
):
    if start_date.weekday() != day.value:
        raise ValueError("Start date must be the same day as the day of the week")

    def weekly_decorator(func: MailGenerationFunc):
        _registry[(system, name)] = RegistryInfo(
            func,
            "weekly",
            retry_on_empty_send=retry_on_empty_send,
            schedule=DeltaSchedule(TZONE, start_date, day, day_time, relativedelta(weeks=every_n_weeks)),
        )
        return func

    return weekly_decorator


class MonthlyTimerNoWe(DeltaSchedule):
    def __init__(
        self,
        tz: timezone,
        start: datetime,
        day_time: time | None,
        td: timedelta | relativedelta,
        day_of_month: int,
        on_invalid_day_action: INVALID_DAY_ACTIONS = "forward",
    ) -> None:
        super().__init__(
            tz, start, weekday=None, day_time=day_time, td=td, on_invalid_day_action=on_invalid_day_action
        )
        self.day_of_month = day_of_month

    def _next_date(self, dt: datetime) -> datetime:
        s = super()._next_date(dt)
        s2 = s.replace(day=self.day_of_month)
        return s2

    def is_day_allowed(self, day: datetime) -> bool:
        if day.weekday() >= 5:
            return False
        if day in HOLIDAYS:
            return False
        return super().is_day_allowed(day)


class DailyTimerNoWe(DeltaSchedule):
    def __init__(self, tz: timezone, start: datetime, day_time: time | None) -> None:
        super().__init__(
            tz,
            start,
            weekday=None,
            day_time=day_time,
            td=timedelta(days=1),
            on_invalid_day_action="forward",
        )

    def is_day_allowed(self, day: datetime) -> bool:
        if day.weekday() >= 5:
            return False
        if day in HOLIDAYS:
            return False
        return super().is_day_allowed(day)


def monthly_mail_no_we(
    system: str,
    name: str,
    start_date: datetime,
    day_of_month: int,
    day_time: time | None = None,
    *,
    every_n_months=1,
    on_invalid_day_action: INVALID_DAY_ACTIONS = "forward",
    retry_on_empty_send: bool,
):
    def monthly_decorator(func: MailGenerationFunc):
        _registry[(system, name)] = RegistryInfo(
            func,
            "monthly_no_we",
            retry_on_empty_send=retry_on_empty_send,
            schedule=MonthlyTimerNoWe(
                TZONE,
                start_date,
                day_of_month=day_of_month,
                day_time=day_time,
                td=relativedelta(months=every_n_months),
                on_invalid_day_action=on_invalid_day_action,
            ),
        )
        return func

    return monthly_decorator


def external_schedule_mail(system: str, name: str):
    def external_decorator(func: MailGenerationFunc):
        _registry[(system, name)] = RegistryInfo(func, "external", retry_on_empty_send=False, schedule=None)
        return func

    return external_decorator


class MailInfos(TypedDict):
    system: str
    mail_name: str
    schedule: Schedule | None


def get_mail_infos() -> list[MailInfos]:
    return [MailInfos(system=k[0], mail_name=k[1], schedule=v.schedule) for k, v in _registry.items()]


def get_function_by_alias(alias: str):
    for key, value in _registry.items():
        if key[0] + "_" + key[1] == alias:
            return (key[0], key[1])
    raise KeyError(f"Key {alias} not found")


class EmptyMailException(Exception):
    pass


class SendInfo(NamedTuple):
    nr_ok: int
    nr_failed: int
    nr_skipped: int


async def _mail_messages(
    res: MailMessage
    | Iterable[MailMessage]
    | None
    | Awaitable[MailMessage | Iterable[MailMessage] | None]
    | AsyncIterable[MailMessage]
    | None,
):
    if inspect.isasyncgen(res):
        async for mail in res:
            yield cast(MailMessage, mail)
        return
    real_res = await res if res is not None and isinstance(res, Awaitable) else res
    if real_res is None:
        return
    real_res = [real_res] if isinstance(real_res, MailMessage) else real_res or []
    for m in real_res:  # type: ignore
        yield cast(MailMessage, m)


async def _send_mails(
    context: GenerationContext, inf: GenerationInfo, reginf: RegistryInfo, *, max_runtime_in_seconds: float | None
):
    run_id = str(uuid4())
    start = time_module.time()
    context.db.save_execution_start(run_id, inf.system, inf.mail_name)
    res = reginf.func(inf)
    real_res = await res if res is not None and isinstance(res, Awaitable) else res
    if real_res is None:
        real_res = []
    real_res = [real_res] if isinstance(real_res, MailMessage) else real_res or []

    nr_failed = 0
    nr_ok = 0
    nr_skipped = 0
    nr_days_back = 1
    if (
        isinstance(reginf.schedule, DeltaSchedule)
        and isinstance(reginf.schedule.timedelta, relativedelta)
        and reginf.schedule.timedelta.weeks >= 1
    ):
        nr_days_back = 2
    yesterday_utc = datetime.now(TZONE).astimezone(timezone.utc) - timedelta(days=nr_days_back)
    last_saved: datetime | None = None
    had_mail = False
    async for mail in _mail_messages(real_res):
        had_mail = True
        assert inf.system == mail.system
        assert inf.mail_name == mail.entity
        if sent_source := await context.db.was_mail_sent(
            context.get_http_session(), inf.system, inf.mail_name, mail.entity, mail.entity_id, yesterday_utc
        ):
            logger.warning(f"Skipping {inf.system} {inf.mail_name} {mail.entity_id} as it was already sent ({sent_source})")
            nr_skipped += 1
            continue
        res = await mail.send(context.get_http_session())
        context.db.save_mail_sent(run_id, mail.system, inf.mail_name, mail.entity, mail.entity_id, res.ok, res.status)
        if res.ok:
            nr_ok += 1
        else:
            nr_failed += 1
        now = datetime.now(TZONE)
        if last_saved is None or (now - last_saved).total_seconds() > 180:
            await context.db.commit_to_storage(with_parquets=False)
            last_saved = now
        else:
            context.db.commit()

        if max_runtime_in_seconds is not None and time_module.time() - start > max_runtime_in_seconds:
            break

    if reginf.retry_on_empty_send and not had_mail:
        raise EmptyMailException()
    context.db.save_execution_end(
        run_id, inf.system, inf.mail_name, nr_failed=nr_failed, nr_ok=nr_ok, nr_skipped=nr_skipped
    )
    await context.db.commit_to_storage(with_parquets=False)
    context.db.commit()
    return SendInfo(nr_ok, nr_failed, nr_skipped)


async def get_mails_dry(
    context: GenerationContext, system: str, mail_name: str, *, filter: Callable[[MailMessage], bool] | None = None
):
    mail = _registry[(system, mail_name)]
    res = mail.func(GenerationInfo(system, mail_name, dry_run=True, context=context))
    real_res = _mail_messages(res)
    async for m in real_res:
        if filter is None or filter(m):
            yield await m.assure_attachments_loaded()


async def send_mails(context: GenerationContext, system: str, mail_name: str, *, max_runtime_in_seconds: float | None):
    mail = _registry[(system, mail_name)]
    return await _send_mails(
        context,
        GenerationInfo(system, mail_name, dry_run=False, context=context),
        mail,
        max_runtime_in_seconds=max_runtime_in_seconds,
    )


async def get_jobs_todo(dry: bool, context: GenerationContext, *, filter_system: str | None = None, filter_mail: str | None = None):
    from bmsdna.mailing.sendgrid import get_last_sent_date

    now = datetime.now(TZONE)
    for key, item in _registry.items():
        if item.schedule:
            if filter_system is not None and key[0] != filter_system:
                continue
            if filter_mail is not None and key[1] != filter_mail:
                continue
            before_date = item.schedule.calc_last_date(now)
            check_since = item.schedule.calc_last_date(before_date)
            ldt = context.db.get_last_execution_end(key[0], key[1], TZONE)
            sdt = context.db.get_last_execution_start(key[0], key[1], TZONE)
            if sdt and ldt and sdt > ldt:
                ldt = sdt  # if the last execution was not finished, we assume it is still running and will finish
            elif not ldt and sdt:
                ldt = sdt
            if item.schedule.is_due(ldt): # it's due, we double-check if it was sent by sendgrid
                send_grid_date = await get_last_sent_date(
                context.get_http_session(), key[0], key[1], check_since, before_date + timedelta(days=1)
                )
                if send_grid_date == "invalid":
                    send_grid_date = None
                if send_grid_date is not None and (ldt is None or send_grid_date > ldt):
                    ldt = send_grid_date
            if item.schedule.is_due(ldt):
                yield GenerationInfo(key[0], key[1], dry_run=dry, context=context)


def get_next_executions(context: GenerationContext):
    res = []
    for key, item in _registry.items():
        ldt = context.db.get_last_execution_end(key[0], key[1], TZONE)
        if item.schedule:
            exec_date = item.schedule.calc_next_date(ldt)
        else:
            exec_date = None
        res.append(
            {
                "system": key[0],
                "mail_name": key[1],
                "last_executed": ldt,
                "exec_date": exec_date,
            }
        )
    return res
