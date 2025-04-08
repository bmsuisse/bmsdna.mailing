import asyncio

from pydantic import BaseModel
from ..message import FileAttachment
from typing import Literal, Optional, TypeAlias, TypedDict
import json
import aiohttp

is_pydantic_v1 = not hasattr(BaseModel, "model_json_schema")

class ExportError(TypedDict):
    code: str
    message: str


class ExportStatus(TypedDict):
    id: str
    percentComplete: int
    status: Literal["Failed", "NotStarted", "Running", "Succeeded", "Undefined"]
    resourceLocation: str
    expirationTime: str
    error: Optional[ExportError]


class ReportGenerationError(Exception):
    def __init__(self, error: ExportError | ExportStatus) -> None:
        super().__init__((error["code"] + ": " + error["message"] if "code" in error else json.dumps(error)))
        self.api_error = error


POWERBI_FORMATS: TypeAlias = Literal[
    "ACCESSIBLEPDF", "DOCX", "IMAGE", "MHTML", "PDF", "PNG", "PPTX", "XML", "PNG", "CSV", "XLSX"
]


class ParameterValue(BaseModel):
    name: str
    value: str


class PaginatedReportConfig(BaseModel):
    formatSettings: dict = {}
    identities: list[dict] = []
    parameterValues: list[ParameterValue] = []

    def set_parameter_value(self, name: str, value: str):
        has_param = False
        for p in self.parameterValues:
            if p.name == name:
                p.value = value
                has_param = True
        if not has_param:
            self.parameterValues.append(ParameterValue(name=name, value=value))
        return self

    def set_parameters(self, args_as_dict: Optional[dict[str, str]] = None, **kwargs):
        if args_as_dict:
            for k, v in args_as_dict.items():
                self.set_parameter_value(k, v)
        if kwargs:
            for k, v in kwargs.items():
                self.set_parameter_value(k, v)
        return self


class PowerBIPaginatedReportAttachment(FileAttachment):
    paginatedReportConfiguration: PaginatedReportConfig
    format: POWERBI_FORMATS = "PDF"

    def get_error_message(self) -> str:
        import urllib.parse

        msg = "Error generating PowerBI report.\r\n"
        msg += "You can download the report manually from the PowerBI service here:\r\n"
        msg += f"https://app.powerbi.com/groups/{self.group_id}/rdlreports/{self.report_id}"
        if self.paginatedReportConfiguration.parameterValues:
            msg += "?"
            msg += "&".join(
                (
                    f"rp:{p.name}={urllib.parse.quote_plus(p.value)}"
                    for p in self.paginatedReportConfiguration.parameterValues
                )
            )
        return msg

    def __init__(
        self,
        report_id: str,
        group_id: str,
        filename: str,
        *,
        format: POWERBI_FORMATS = "PDF",
        paginatedReportConfiguration: Optional[PaginatedReportConfig] = None,
        report_args: Optional[dict[str, str]] = None,
        api_token: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.report_id = report_id
        self.group_id = group_id
        self.format = format
        self.paginatedReportConfiguration = paginatedReportConfiguration or PaginatedReportConfig()
        if report_args:
            self.paginatedReportConfiguration.set_parameters(report_args)
        self._token = api_token
        self._filename = filename

    async def get_content(self) -> bytes:
        if isinstance(self.content, bytes):
            return self.content
        if not self._token:
            from ..basicazure import acquire_token, POWERBI_API_SCOPE

            token, exp_dt = await acquire_token(prefix="POWERBI", scopes=POWERBI_API_SCOPE)
            self._token = token
        headers = {"Authorization": "Bearer " + self._token}

        async with aiohttp.ClientSession() as session:
            config = self.paginatedReportConfiguration.model_dump() if not is_pydantic_v1 else self.paginatedReportConfiguration.dict()
            
            res = await session.post(
                f"https://api.powerbi.com/v1.0/myorg/groups/{self.group_id}/reports/{self.report_id}/ExportTo",
                headers=headers,
                json={
                    "format": self.format,
                    "paginatedReportConfiguration":config,
                },
            )
            if res.status > 299:
                print(await res.text())
            res.raise_for_status()
            jsd: ExportStatus = await res.json()
            export_id = jsd["id"] if "id" in jsd else None
            print(json.dumps(jsd))
            res.raise_for_status()
            if jsd["status"] == "Failed":
                raise ValueError(jsd["status"])
            else:
                status = jsd["status"]
                cnt = 0
                while status not in ["Failed", "Succeeded"]:
                    cnt += 1
                    await asyncio.sleep(10)
                    status_url = f"https://api.powerbi.com/v1.0/myorg/groups/{self.group_id}/reports/{self.report_id}/exports/{export_id}"
                    res = await session.get(status_url, headers=headers)
                    res.raise_for_status()
                    jsd: ExportStatus = await res.json()
                    if cnt == 1 or cnt % 10 == 0:
                        print(json.dumps(jsd))
                    status = jsd["status"]
            if status == "Succeeded":
                res = await session.get(jsd["resourceLocation"], headers=headers)
                res.raise_for_status()
                self.content = await res.read()
                return self.content
            elif status == "Failed":
                assert jsd is not None
                raise ReportGenerationError(jsd.get("error", jsd) or jsd)
            else:
                raise ValueError("Status not found")
