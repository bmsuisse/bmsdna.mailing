from datetime import datetime, timezone
from datetime import time
from typing import AsyncIterable, TypeVar
from bmsdna.mailing.generation_context import GenerationContext
from bmsdna.mailing.persistance import PersistanceDB
from bmsdna.mailing.registry import get_jobs_todo
import pytest
import os

from bmsdna.mailing.registry import TZONE, GenerationInfo, monthly_mail_no_we
from bmsdna.mailing.storage import _get_container_client, get_database

T = TypeVar("T")


async def _list(l: AsyncIterable[T]):
    return [x async for x in l]


@pytest.mark.asyncio
async def test_db():
    @monthly_mail_no_we(
        "system_name",
        "periodic_mail_name",
        start_date=datetime(2023, 1, 1, 8, 0, tzinfo=TZONE),
        day_of_month=1,
        day_time=time(8, 0, tzinfo=TZONE),
        on_invalid_day_action="backward",
        retry_on_empty_send=False,
    )
    def _generate_mail(info: GenerationInfo) -> None:
        pass

    os.environ["MAIL_STORAGE_CONNECTION"] = "UseDevelopmentStorage=true"
    async with _get_container_client() as cc:
        try:
            await cc.delete_container()
        except:
            pass
        await cc.create_container()
    lcpath = await get_database("maildb")
    try:
        os.unlink(lcpath)
    except:
        pass
    async with GenerationContext() as genc:
        pers_db = genc.db

        todos = await _list(get_jobs_todo(True, genc))
        tm = [t for t in todos if t.system == "system_name" and t.mail_name == "periodic_mail_name"]
        assert len(tm) == 1

        start_db = datetime.now(tz=timezone.utc)
        pers_db.save_execution_start("run_id", "system_name", "periodic_mail_name")

        l1 = pers_db.get_logs(start_db)
        assert len(l1) == 1
        assert l1[0]["RowKey"] == "run_id"
        assert l1[0]["PartitionKey"] == "system_name_periodic_mail_name"
        assert l1[0].get("nr_failed") is None
        assert l1[0].get("nr_ok") is None
        assert l1[0].get("start") is not None
        assert l1[0].get("end") is  None

        todos = await _list(get_jobs_todo(True, genc))
        tm = [t for t in todos if t.system == "system_name" and t.mail_name == "periodic_mail_name"]
        assert len(tm) == 0

        pers_db.save_execution_end("run_id", "system_name", "periodic_mail_name", 1, 3, nr_skipped=5)
        l = pers_db.get_logs(start_db)
        assert len(l) == 1
        assert l[0]["RowKey"] == "run_id"
        assert l[0]["PartitionKey"] == "system_name_periodic_mail_name"
        assert l[0]["nr_failed"] == 1
        assert l[0]["nr_ok"] == 3
        assert l[0]["nr_skipped"] == 5
        assert l[0]["start"] is not None
        assert l[0]["end"] is not None
        last_end =  l[0]["end"]

        todos = await _list(get_jobs_todo(True, genc))
        tm = [t for t in todos if t.system == "system_name" and t.mail_name == "periodic_mail_name"]
        
        assert len(tm) == 0
        le = pers_db.get_last_execution_end("system_name", "periodic_mail_name", TZONE)
        assert le ==  last_end

    try:
        os.unlink(lcpath)
    except:
        pass
    async with (
        GenerationContext() as genc
    ):  # should still be zero, as we do need to refresh the file from blob storage
        todos = await _list(get_jobs_todo(True, genc))
        tm = [t for t in todos if t.system == "system_name" and t.mail_name == "periodic_mail_name"]
        assert len(tm) == 0
