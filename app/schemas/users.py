from typing import Optional, Union

from pydantic import BaseModel

from app.schemas.base import APIBaseCreateSchema, APIBaseSchema
from app.schemas.servers import ServerMemberSchema


class UserSchema(APIBaseSchema):
    display_name: Optional[str]
    wallet_address: Optional[str]
    email: Optional[str]

    status: Optional[str]

    class Config:
        schema_extra = {
            "example": {
                "id": "61e17018c3ee162141baf5c8",
                "display_name": "vitalik.eth",
                "wallet_address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                "email": "test@newshades.xyz",
                "status": "online",
            }
        }


class UserCreateSchema(APIBaseCreateSchema):
    display_name: Optional[str] = ""
    wallet_address: str = ""

    class Config:
        schema_extra = {
            "example": {
                "display_name": "vitalik",
                "wallet_address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                "email": "test@newshades.xyz",
            }
        }


class UserUpdateSchema(APIBaseCreateSchema):
    display_name: Optional[str]


class EitherUserProfile(BaseModel):
    __root__: Union[ServerMemberSchema, UserSchema]
