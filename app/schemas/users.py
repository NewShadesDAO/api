from typing import List, Optional, Union

from pydantic import BaseModel

from app.schemas.base import APIBaseCreateSchema, APIBaseSchema, PyObjectId
from app.schemas.servers import ServerMemberSchema


class UserSchema(APIBaseSchema):
    display_name: Optional[str]
    wallet_address: Optional[str]
    ens_domain: Optional[str]
    email: Optional[str]
    pfp: Optional[dict]
    status: Optional[str]
    description: Optional[str]

    class Config:
        schema_extra = {
            "example": {
                "id": "61e17018c3ee162141baf5c8",
                "display_name": "vitalik",
                "ens_domain": "vitalik.eth",
                "description": "hello!",
                "wallet_address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                "email": "test@newshades.xyz",
                "pfp": {
                    "cf_id": "5adcdc13-0a45-45cd-0707-31eab9997c00",
                    "contract": "0x58f7e9810f5559dc759b731843212370363e433e",
                    "token_id": "100",
                    "token": {},
                    "verified": True,
                    "input": "https://opensea.io/assets/0x58f7e9810f5559dc759b731843212370363e433e/100",
                    "input_image_url": "https://cloudflare-ipfs.com/ipfs/.../image.png",
                },
                "status": "online",
            }
        }


class UserCreateSchema(APIBaseCreateSchema):
    display_name: Optional[str] = ""
    wallet_address: str = ""
    description: Optional[str] = ""

    class Config:
        schema_extra = {
            "example": {
                "display_name": "vitalik",
                "wallet_address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                "description": "I am the creator of ETH!",
            }
        }


class UserUpdateSchema(APIBaseCreateSchema):
    display_name: Optional[str]
    ens_domain: Optional[str]
    pfp: Optional[str]
    description: Optional[str]


class EitherUserProfile(BaseModel):
    __root__: Union[ServerMemberSchema, UserSchema]


class RoleSchema(APIBaseSchema):
    server: PyObjectId
    name: str
    permissions: List[str]


class RoleCreateSchema(APIBaseCreateSchema):
    name: str
    server: Optional[str]
    permissions: List[str]
