from datetime import datetime
from datetime import time
from bmsdna.mailing.generation_context import GenerationContext
from bmsdna.mailing.message import MailMessage
from bmsdna.mailing.registry import send_mails
import pytest

from bmsdna.mailing.registry import TZONE, GenerationInfo, daily_mail


@pytest.mark.asyncio
async def test_double_send():
    @daily_mail(
        "test_system",
        "test_periodic_mail",
        start_date=datetime(2023, 1, 1, 8, 0, tzinfo=TZONE),
        day_time=time(8, 0, tzinfo=TZONE),
        retry_on_empty_send=False,
    )
    def _generate_mail(info: GenerationInfo):
        return MailMessage(
            entity="test_periodic_mail",
            entity_id="test_entity_id",
            system="test_system",
            subject="test_subject",
            body="test_body",
            body_is_html=False,
            to="holzöpfl_zipflchape@bmsuisse.ch",
        )

    async with GenerationContext() as genc:
        genc.db.init_db()
        si = await send_mails(genc, "test_system", "test_periodic_mail", max_runtime_in_seconds=20)
        assert si.nr_ok == 1
        assert si.nr_failed == 0
        assert si.nr_skipped == 0
        si = await send_mails(genc, "test_system", "test_periodic_mail", max_runtime_in_seconds=20)
        assert si.nr_ok == 0
        assert si.nr_failed == 0
        assert si.nr_skipped == 1

    async with GenerationContext() as genc:
        si = await send_mails(genc, "test_system", "test_periodic_mail", max_runtime_in_seconds=20)
        assert si.nr_ok == 0
        assert si.nr_failed == 0
        assert si.nr_skipped == 1
