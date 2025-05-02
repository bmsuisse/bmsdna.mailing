from .message import MailMessage
from .message_io import write_eml_file
import os
from datetime import timezone, datetime
import uuid
import io
import aiofiles
import logging

logger = logging.getLogger(__name__)

container_name = "mail"


def _get_container_client():
    from azure.storage.blob.aio import ContainerClient
    from bmsdna.mailing.config import get_async_default_credential

    account_name = os.getenv("MAIL_STORAGE_ACCOUNT")
    if account_name:
        return ContainerClient(account_name + ".blob.core.windows.net", container_name, credential=get_async_default_credential())
    constr = os.getenv("MAIL_STORAGE_CONNECTION", os.getenv("AzureWebJobsStorage"))
    if constr == "UseDevelopmentStorage=true":
        constr = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;"
    assert constr is not None
    if os.getenv("IS_DEV") == "1":
        from azure.storage.blob import ContainerClient as ContainerClientSync

        with ContainerClientSync.from_connection_string(constr, container_name) as cs:
            if not cs.exists():
                cs.create_container()
    return ContainerClient.from_connection_string(constr, container_name)


def _get_container_client_sync():
    from azure.storage.blob import ContainerClient as ContainerClientSync
    from bmsdna.mailing.config import get_default_credential


    if account_name := os.getenv("MAIL_STORAGE_ACCOUNT"):
        return ContainerClientSync(account_name + ".blob.core.windows.net", container_name, credential=get_default_credential())
    constr = os.getenv("MAIL_STORAGE_CONNECTION", os.getenv("AzureWebJobsStorage"))
    if constr == "UseDevelopmentStorage=true":
        constr = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;QueueEndpoint=http://127.0.0.1:10001/devstoreaccount1;TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;"
    assert constr is not None
    if os.getenv("IS_DEV") == "1":
        with ContainerClientSync.from_connection_string(constr, container_name) as cs:
            if not cs.exists():
                cs.create_container()
    return ContainerClientSync.from_connection_string(constr, container_name)


async def save_sent_mail(m: MailMessage):
    async with _get_container_client() as contc:
        datepath = datetime.now().strftime("%Y/%m/%d/%H%M")
        emailid = str(m.email_id or uuid.uuid4())
        path = f"sent/{m.system}/{m.entity}/{datepath}/{m.entity_id}_{emailid}.eml"
        async with contc.get_blob_client(path) as bc:
            with io.BytesIO() as bio:
                await write_eml_file(m, bio)
                bio.seek(0)
                await bc.upload_blob(bio)


async def save_mail_failure(
    m: MailMessage, status: int, binary_response: bytes, content_type: str, json_data: str | None
):
    async with _get_container_client() as contc:
        datepath = datetime.now().strftime("%Y/%m/%d/%H%M")
        emailid = str(m.email_id or uuid.uuid4())
        path = f"error/{m.system}/{m.entity}/{datepath}/{m.entity_id}_{emailid}.eml"
        path_error = f"error/{m.system}/{m.entity}/{datepath}/{m.entity_id}_{emailid}.txt"
        path_error2 = f"error/{m.system}/{m.entity}/{datepath}/{m.entity_id}_{emailid}.json"
        async with contc.get_blob_client(path) as bc:
            with io.BytesIO() as bio:
                await write_eml_file(m, bio)
                bio.seek(0)
                await bc.upload_blob(bio)
        async with contc.get_blob_client(path_error) as bc:
            await bc.upload_blob(binary_response)
        if json_data is not None:
            async with contc.get_blob_client(path_error2) as bc:
                await bc.upload_blob(json_data)

    logger.error("Could not send mail: " + binary_response.decode("utf-8"))


async def get_database(db_name: str, force=False, old=False):
    async with _get_container_client() as contc:
        path = db_name
        localpath = os.getenv("TEMP", "/tmp") + "/" + db_name
        os.makedirs(localpath, exist_ok=True)
        try:
            if not await contc.exists():
                await contc.create_container()
        except Exception:
            pass
        async for item in contc.list_blobs(path):
            assert item.name is not None
            if item.name.endswith(".old") and not old:
                continue
            if old and not item.name.endswith(".old"):
                continue
            assert item.last_modified is not None
            last_mod: datetime = item.last_modified
            if last_mod.tzinfo is None:
                last_mod = last_mod.astimezone(timezone.utc)

            fname = item.name.split("/")[-1]
            full_local_path = os.path.join(localpath, fname)
            if old and full_local_path.endswith(".old"):
                full_local_path = full_local_path[:-4]
            if os.path.exists(full_local_path) and not force:
                lmod = datetime.fromtimestamp(os.path.getmtime(full_local_path))
                if lmod.tzinfo is None:
                    lmod = lmod.astimezone(timezone.utc)
                if lmod > last_mod:
                    continue
            res = await contc.download_blob(item.name)
            async with aiofiles.open(full_local_path, "wb") as f:
                b = await res.read(4048)
                while b:
                    await f.write(b)
                    b = await res.read(4048)
        return localpath + "/" + db_name + ".sqlite"


def get_database_sync(db_name: str):
    with _get_container_client_sync() as contc:
        path = db_name
        localpath = os.getenv("TEMP", "/tmp") + "/" + db_name
        os.makedirs(localpath, exist_ok=True)
        for item in contc.list_blobs(path):
            assert item.name is not None
            assert item.last_modified is not None
            last_mod: datetime = item.last_modified
            if last_mod.tzinfo is None:
                last_mod = last_mod.astimezone(timezone.utc)

            fname = item.name.split("/")[-1]
            full_local_path = os.path.join(localpath, fname)
            if os.path.exists(full_local_path):
                lmod = datetime.fromtimestamp(os.path.getmtime(full_local_path))
                if lmod.tzinfo is None:
                    lmod = lmod.astimezone(timezone.utc)
                if lmod > last_mod:
                    continue
            res = contc.download_blob(item.name)
            with open(full_local_path, "wb") as f:
                b = res.read(4048)
                while b:
                    f.write(b)
                    b = res.read(4048)
        return localpath + "/" + db_name + ".sqlite"


async def write_database(db_name: str):
    async with _get_container_client() as contc:
        localpath = os.getenv("TEMP", "/tmp") + "/" + db_name
        os.makedirs(localpath, exist_ok=True)
        for item in os.listdir(localpath):
            if not item.endswith(".old"):
                full_path = os.path.join(localpath, item)
                async with aiofiles.open(full_path, "rb") as f:
                    async with contc.get_blob_client(db_name + "/" + item) as cl:
                        if await cl.exists():
                            async with contc.get_blob_client(db_name + "/" + item + ".old") as cl2:
                                await cl2.upload_blob(await (await cl.download_blob()).readall(), overwrite=True)

                        await cl.upload_blob(f, overwrite=True)
