import asyncio
from datetime import datetime, timezone
import os
from typing import Awaitable, Callable, Literal, TypeVar
import aiohttp


async def retry_many(func: Callable[[], Awaitable[aiohttp.ClientResponse]]) ->aiohttp.ClientResponse:
    for i in range(9):
        rsp = await func()
        if rsp.status == 429:
            await asyncio.sleep(2 ** i)
        else:
            return rsp
    return await func()

async def get_is_mail_sent(http_session: aiohttp.ClientSession, system: str, mail: str, entity_id: str):
    api_key = os.getenv("SENDGRID_API_KEY")
    if not api_key:
        return False
    headers = {"Authorization": "Bearer " + api_key}
    assert '"' not in system
    assert '"' not in mail
    assert '"' not in entity_id
    query = f"(unique_args['system']=\"{system}\") AND (unique_args['entity']=\"{mail}\") AND (unique_args['entity_id']=\"{entity_id}\")"
    async def _load_base():
        return await http_session.get("https://api.sendgrid.com/v3/messages", params={"query": query, "limit": "2"}, headers=headers)
    rsp = await retry_many(_load_base) 
    rsp.raise_for_status()
    jsd = await rsp.json()
    return len(jsd["messages"]) > 0


async def get_last_sent_date(
    http_session: aiohttp.ClientSession,
    system: str,
    mail: str,
    since: datetime | str,
    stop_if_gte: datetime | None = None,
) -> datetime | None | Literal["invalid"]:
    api_key = os.getenv("SENDGRID_API_KEY")
    if not api_key:
        return "invalid"
    since_str = (
        since.astimezone(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if not isinstance(since, str) else since
    )
    query = f'(unique_args[\'system\']="{system}") ANd (unique_args[\'entity\']="{mail}") AND last_event_time >= TIMESTAMP "{since_str}"'
    headers = {"Authorization": "Bearer " + api_key}
    async def _load_base():
        return await http_session.get(
            "https://api.sendgrid.com/v3/messages", params={"query": query, "limit": 1000}, headers=headers
        )
    rsp = await retry_many(_load_base)
    if rsp.status >= 300:
        print(await rsp.text())
    rsp.raise_for_status()
    jsd = await rsp.json()
    if len(jsd["messages"]) == 0:
        return None
    max_date = None
    msg_cnt = 0
    all_msgs : list[dict]= jsd["messages"]
    all_msgs.sort(key=lambda x: datetime.fromisoformat(x["last_event_time"]), reverse=True)
    for msg in all_msgs:
        if msg["status"] == "processing":
            date_str = msg["last_event_time"]
        else:
            msg_cnt += 1
            if msg_cnt > 10:
                return max_date
            rsp_msg = await http_session.get(f"https://api.sendgrid.com/v3/messages/{msg['msg_id']}", headers=headers)
            if rsp_msg.status == 429:  # I'm not getting a price for this, but hey, it works
                await asyncio.sleep(10)
                rsp_msg = await http_session.get(
                    f"https://api.sendgrid.com/v3/messages/{msg['msg_id']}", headers=headers
                )
                if rsp_msg.status == 429:
                    await asyncio.sleep(20)
                    rsp_msg = await http_session.get(
                        f"https://api.sendgrid.com/v3/messages/{msg['msg_id']}", headers=headers
                    )
                    if rsp_msg.status == 429:
                        await asyncio.sleep(60)
                        rsp_msg = await http_session.get(
                            f"https://api.sendgrid.com/v3/messages/{msg['msg_id']}", headers=headers
                        )
                        if rsp_msg.status == 429:
                            return max_date

            rsp_msg.raise_for_status()
            msg_js = await rsp_msg.json()
            process_date = next((x for x in msg_js["events"] if x["event_name"] == "processed"))["processed"]
            date_str = process_date
        date_time = datetime.fromisoformat(date_str)
        if max_date is None or date_time > max_date:
            max_date = date_time
            if stop_if_gte is not None and max_date > stop_if_gte:
                return max_date
    return max_date
