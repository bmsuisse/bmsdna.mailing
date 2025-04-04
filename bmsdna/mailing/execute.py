import time
from .storage import _get_container_client
from .registry import get_jobs_todo, send_mails
from .generation_context import GenerationContext
import logging
import sys
import traceback

logger = logging.getLogger(__name__)


async def run_jobs(
    max_runtime_in_seconds: int | None = None, *, filter_system: str | None = None, filter_mail: str | None = None
):
    from .registry import EmptyMailException

    errors = []
    all_oks = 0
    all_failes = 0
    all_empty = 0
    all_skipped = 0
    results = []
    start = time.time()
    async with _get_container_client() as contc:

        async with GenerationContext() as context:
            async for td in get_jobs_todo(dry=False, context=context, filter_system=filter_system, filter_mail=filter_mail):
                if filter_system is not None and td.system != filter_system:
                    continue
                if filter_mail is not None and td.mail_name != filter_mail:
                    continue
                async with contc.get_blob_client(f"lock_{td.system}__{td.mail_name}.txt") as bc:
                    if not await bc.exists():
                        await bc.upload_blob("empty")
                    async with await bc.acquire_lease(lease_duration=60) as lease:
                        try:
                            timeout_in_s = (
                                max_runtime_in_seconds - (time.time() - start)
                                if max_runtime_in_seconds is not None
                                else None
                            )
                            nr_ok, nr_failed, nr_skipped = await send_mails(
                                context, td.system, td.mail_name, max_runtime_in_seconds=timeout_in_s
                            )
                            results.append(
                                {
                                    "mail": f"{td.system}/{td.mail_name}",
                                    "ok": nr_ok,
                                    "failed": nr_failed,
                                    "skipped": nr_skipped,
                                }
                            )
                            all_oks += nr_ok
                            all_failes += nr_failed
                            all_skipped += nr_skipped
                        except EmptyMailException:
                            logger.warning(f"No mails to send for {td.system}/{td.mail_name}")
                            results.append(
                                {"mail": f"{td.system}/{td.mail_name}", "ok": 0, "failed": 0, "empty": "empty"}
                            )
                            all_empty += 1
                        except Exception as err:
                            logger.error("Error in send_mails", exc_info=err)
                            errors.append(err)
                            results.append(
                                {"mail": f"{td.system}/{td.mail_name}", "ok": 0, "failed": 1, "err": str(err)}
                            )
                            async with contc.get_blob_client(
                                f"last_run_error/{td.system}/{td.mail_name}_error.txt"
                            ) as bc:
                                err_str = repr(err) + "\r\n\r\n" + traceback.format_exc()
                                await bc.upload_blob(err_str, overwrite=True)
                        if max_runtime_in_seconds is not None and time.time() - start > max_runtime_in_seconds:
                            logger.warning(f"Max runtime of {max_runtime_in_seconds} seconds reached")
                            await context.db.commit_to_storage(with_parquets=True)
                            break
                        else:
                            await lease.renew()
                            await context.db.commit_to_storage(with_parquets=False)
                    await context.db.commit_to_storage(with_parquets=True)

    if len(errors) == 1:
        raise errors[0]
    elif len(errors) > 1:
        if sys.version_info > (3, 11):
            raise ExceptionGroup("Errors in run_jobs", errors)
        else:
            raise errors[0]
    elif all_failes > 0:
        raise Exception(f"{all_failes} mails failed to send. See Logs in funcstore/error")
    return results
