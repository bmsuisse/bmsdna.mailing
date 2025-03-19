import os
from typing import cast, TYPE_CHECKING

import pytest
from dotenv import load_dotenv

load_dotenv()

if TYPE_CHECKING:
    from docker.models.containers import Container


def start_azurite() -> "Container":
    import docker
    import docker.errors
    from docker.models.containers import Container

    client = docker.from_env()  # code taken from https://github.com/fsspec/adlfs/blob/main/adlfs/tests/conftest.py#L72
    azurite_server: Container | None = None
    try:
        m = cast(Container, client.containers.get("test4azurite"))
        if m.status == "running":
            return m
        else:
            azurite_server = m
    except docker.errors.NotFound:
        pass

    if azurite_server is None:
        azurite_server = client.containers.run(
            "mcr.microsoft.com/azure-storage/azurite:latest",
            detach=True,
            name="test4azurite",
            ports={"10000/tcp": 10000, "10001/tcp": 10001, "10002/tcp": 10002},
        )  # type: ignore
    assert azurite_server is not None
    azurite_server.start()
    print(azurite_server.status)
    print("Successfully created azurite container...")
    return azurite_server


@pytest.fixture(scope="session", autouse=True)
def spawn_azurite():
    if os.getenv("NO_AZURITE_DOCKER", "0") == "1":
        yield None
    else:
        azurite = start_azurite()
        yield azurite
        if os.getenv("KEEP_AZURITE_DOCKER", "0") == "0":  # can be handy during development
            azurite.stop()

@pytest.fixture(scope="session", autouse=True)
def init_azurite(spawn_azurite):
    from azure.data.tables import TableServiceClient
    azurite_con_str = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;TableEndpoint=http://127.0.0.1:10002/devstoreaccount1;"
    table_service_client = TableServiceClient.from_connection_string(azurite_con_str)
    try:
        table_service_client.get_table_client("periodMailLog").delete_table()
    except Exception:
        pass
    try:
        table_service_client.get_table_client("mailSentLog").delete_table()
    except Exception:
        pass