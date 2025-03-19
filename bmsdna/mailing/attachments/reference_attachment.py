from typing import Literal
from ..message import BaseAttachment


# THIS IS UNTESTED AND MS-GRAPH ONLY
class ReferenceAttachment(BaseAttachment):
    def __init__(
        self,
        name: str,
        *,
        source_url: str,
        provider_type: Literal["oneDriveBusiness", "oneDriveConsumer", "dropbox", "other"],
        permission: Literal[
            "other", "view", "edit", "anonymousView", "anonymousEdit", "organizationView", "organizationEdit"
        ],
        is_folder: bool = False,
    ) -> None:
        super().__init__()
        self.name = name
        self.source_url = source_url
        self.provider_type = provider_type
        self.permission = permission
        self.is_folder = is_folder

    def get_error_message(self) -> str:
        # not really needed
        return f"Error loading attachment {self.name} from {self.source_url}"

    async def assure_persisted_content(self):
        return 1  # nothing to persist here

    def serialize4json(self, flavor: Literal["msgraph", "sendgrid"]) -> dict:
        if flavor == "sendgrid":
            raise ValueError("ReferenceAttachment is not supported in SendGrid")
        return {
            "@odata.type": "#microsoft.graph.referenceAttachment",
            "name": self.name,
            "sourceUrl": self.source_url,
            "providerType": self.provider_type,
            "permission": self.permission,
            "isFolder": self.is_folder,
        }
