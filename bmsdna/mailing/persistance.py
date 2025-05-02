from uuid import uuid4
from azure.data.tables import TableServiceClient, TableClient, UpdateMode
from azure.core.exceptions import ResourceExistsError
from datetime import datetime, timezone
import aiohttp
import os
import logging


IS_DEV = os.getenv("IS_DEV") in ["True", "true", "1", "TRUE"]
IS_TEST = os.getenv("IS_TEST") in ["True", "true", "1", "TRUE"]

logger = logging.getLogger(__name__)

def get_table_service():
    from bmsdna.mailing.config import get_default_credential
    short_azurite_constr = "UseDevelopmentStorage=true"
    azurite_con_str = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;"
    
    if constr := os.getenv("AZURE_TABLE_CONNECTION_STRING"):
        if constr == short_azurite_constr:
            constr = azurite_con_str
        return TableServiceClient.from_connection_string(constr)
    elif endpoint := os.getenv("AZURE_TABLE_ENDPOINT"):
        return TableServiceClient(endpoint=endpoint, credential=get_default_credential())
    elif account_name := os.getenv("MAIL_STORAGE_ACCOUNT"):
        return TableServiceClient(endpoint=f"https://{account_name}.table.core.windows.net", credential=get_default_credential())
    elif IS_DEV or IS_TEST:
        return TableServiceClient.from_connection_string(azurite_con_str)
    else:
        raise ValueError("No AZURE_TABLE_CONNECTION_STRING or AZURE_TABLE_ENDPOINT provided")

class PersistanceDB:
    def __init__(self, read_only: bool = False) -> None:
        self.read_only = read_only
        self.db_dirty = False

    def init_db(self):
        assert self.period_mail_log_table is not None
        assert self.mail_sent_log_table is not None
        try:
            self.period_mail_log_table.create_table()
        except ResourceExistsError:
            pass
        except Exception as err:
            logger.warning("Could not create table. Assuming it exists", exc_info=err)
            
        try:
            self.mail_sent_log_table.create_table()
        except ResourceExistsError:
            pass
        except Exception as err:
            logger.warning("Could not create table. Assuming it exists", exc_info=err)

    def commit(self):
        pass

    async def __aenter__(self, *args, **kwargs):
        self._table_service = get_table_service()
        
        self.period_mail_log_table = self._table_service.get_table_client("periodMailLog")
        self.mail_sent_log_table = self._table_service.get_table_client("mailSentLog")

        self.init_db()
        return self

    async def _create_parquets(self):
        import polars as pl
        from .storage import _get_container_client
        assert self.period_mail_log_table is not None
        assert self.mail_sent_log_table is not None
        async with _get_container_client() as contc:
            since = None
            async for blob in contc.list_blobs("mailparquets/period_mail_log"):
                since = blob["last_modified"] if since is None else max(since, blob["last_modified"])

            query_filter = f"start ge datetime'{since.isoformat()}'" if since else "start ge datetime'2000-01-01T00:00:00Z'"
            entities = self.period_mail_log_table.query_entities(query_filter)
            all_df = pl.DataFrame([entity for entity in entities])

            temp_file = os.path.join(os.getenv("TEMP", "/tmp"), str(uuid4()) + ".parquet")
            if not all_df.is_empty():
                all_df.write_parquet(temp_file)
                now = datetime.now(tz=timezone.utc).strftime("%Y/%m/%d/%H%M/%S_")
                async with contc.get_blob_client(f"mailparquets/period_mail_log/{now}.parquet") as bc:
                    with open(temp_file, "rb") as f:
                        await bc.upload_blob(f, overwrite=True)
                os.remove(temp_file)

            since = None
            async for blob in contc.list_blobs("mailparquets/mail_sent_log"):
                since = blob["last_modified"] if since is None else max(since, blob["last_modified"])

            query_filter = f"sent_at ge datetime'{since.isoformat()}'" if since else "sent_at ge datetime'2000-01-01T00:00:00Z'"
            entities = self.mail_sent_log_table.query_entities(query_filter)
            all_df = pl.DataFrame([entity for entity in entities])

            temp_file = os.path.join(os.getenv("TEMP", "/tmp"), str(uuid4()) + ".parquet")
            if not all_df.is_empty():
                all_df.write_parquet(temp_file)
                now = datetime.now(tz=timezone.utc).strftime("%Y/%m/%d/%H%M/%S_")
                async with contc.get_blob_client(f"mailparquets/mail_sent_log/{now}.parquet") as bc:
                    with open(temp_file, "rb") as f:
                        await bc.upload_blob(f, overwrite=True)
                os.remove(temp_file)

    async def commit_to_storage(self, with_parquets: bool = True, reopen=True):
        if self.db_dirty and with_parquets:
            await self._create_parquets()
            self.db_dirty = False

    def save_execution_start(self, run_id: str, system_name: str, periodic_mail_name: str):
        assert self.period_mail_log_table is not None
        assert self.mail_sent_log_table is not None
        if self.read_only:
            raise ValueError("Cannot execute in readonly")
        self.db_dirty = True
        entity = {
            "PartitionKey": system_name + "_" + periodic_mail_name,
            "RowKey": run_id,
            "start": datetime.now(tz=timezone.utc)
        }
        self.period_mail_log_table.create_entity(entity)

    def get_logs(self, since: datetime):
        assert self.period_mail_log_table is not None
        assert self.mail_sent_log_table is not None
        query_filter = f"start ge datetime'{since.isoformat()}'"
        entities = self.period_mail_log_table.query_entities(query_filter)
        return [entity for entity in entities]

    def save_execution_end(self, run_id: str, system_name: str, periodic_mail_name: str, nr_failed: int, nr_ok: int, nr_skipped: int):
        self.db_dirty = True
        assert self.period_mail_log_table is not None
        assert self.mail_sent_log_table is not None
        if self.read_only:
            raise ValueError("Cannot execute in readonly")
        self.period_mail_log_table.update_entity({
            "PartitionKey": system_name + "_" + periodic_mail_name,
            "RowKey": run_id,
                "end": datetime.now(tz=timezone.utc),
                "nr_failed": nr_failed,
                "nr_ok": nr_ok,
                "nr_skipped": nr_skipped

        })

    def get_last_execution_start(self, system_name: str, periodic_mail_name: str, tzone: timezone):
        assert self.period_mail_log_table is not None
        assert self.mail_sent_log_table is not None
        part_key = system_name + "_" + periodic_mail_name
        query_filter = f"PartitionKey eq '{part_key}'"
        entities = self.period_mail_log_table.query_entities(query_filter, select=["start"])
        last_start = None
        for entity in entities:
            start = datetime.fromisoformat(entity["start"]).astimezone(tzone) if not isinstance(entity["start"], datetime) else entity["start"].astimezone(tzone)
            if not last_start or start > last_start:
                last_start = start
        return last_start

    async def was_mail_sent(self, session: aiohttp.ClientSession, system_name: str, periodic_mail_name: str, entity: str, entity_id: str, after: datetime):
        assert self.period_mail_log_table is not None
        assert self.mail_sent_log_table is not None
        part_key =system_name + "_" + periodic_mail_name
        row_key = entity + "_" + entity_id
        query_filter = f"ok eq true and PartitionKey eq '{part_key}' and RowKey eq '{row_key}'"
        entities = self.mail_sent_log_table.query_entities(query_filter)
        if any(entities):
            return "azure_table"

        from bmsdna.mailing.sendgrid import get_is_mail_sent
        try:
            if await get_is_mail_sent(session, system_name, periodic_mail_name, entity_id):
                return "sendgrid"
        except aiohttp.ClientResponseError:
            logger.warning("Error while checking mail sent status")
            return False
        return False

    def save_mail_sent(self, run_id: str, system_name: str, periodic_mail_name: str, entity: str, entity_id: str, ok: bool, status: int):
        self.db_dirty = True
        assert self.period_mail_log_table is not None
        assert self.mail_sent_log_table is not None
        if self.read_only:
            raise ValueError("Cannot execute in readonly")
        self.mail_sent_log_table.create_entity({
            "PartitionKey": system_name + "_" + periodic_mail_name,
            "RowKey": entity + "_" + entity_id,
            "run_id": run_id,
            "ok": ok,
            "status": status,
            "sent_at": datetime.now(tz=timezone.utc)
        })

    def get_last_execution_end(self, system_name: str, periodic_mail_name: str, tzone: timezone):
        part_key =system_name + "_" + periodic_mail_name
        assert self.period_mail_log_table is not None
        assert self.mail_sent_log_table is not None

        query_filter = f"PartitionKey eq '{part_key}'"
        entities = self.period_mail_log_table.query_entities(query_filter, select=["end"])
        last_end = None 
        for entity in entities:
            if end_dts := entity.get("end"):
                if end_dts is None:
                    continue
                end_dt = datetime.fromisoformat(end_dts).astimezone(tzone) if not isinstance(end_dts, datetime) else end_dts.astimezone(tzone)
                if not last_end or end_dt > last_end:
                    last_end = end_dt
        return last_end

    async def __aexit__(self, *args, **kwargs):
        await self.commit_to_storage(reopen=False)

        if self.period_mail_log_table is not None:
            self.period_mail_log_table.close()
        if self.mail_sent_log_table is not None:
            self.mail_sent_log_table.close()
        if self._table_service is not None:
            self._table_service.close()
        self.period_mail_log_table = None
        self.mail_sent_log_table = None
        self._table_service = None

