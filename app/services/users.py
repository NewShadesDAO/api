import http
import logging
from typing import Optional, Union

from bson import ObjectId
from fastapi import HTTPException

from app.helpers.pfp import extract_contract_and_token_from_string, upload_pfp_url_and_update_profile
from app.helpers.queue_utils import queue_bg_task
from app.helpers.w3 import checksum_address, get_nft, get_nft_image_url, verify_token_ownership
from app.helpers.ws_events import WebSocketServerEvent
from app.models.base import APIDocument
from app.models.channel import ChannelReadState
from app.models.server import ServerMember
from app.models.user import User
from app.schemas.servers import ServerMemberUpdateSchema
from app.schemas.users import UserCreateSchema, UserUpdateSchema
from app.services.crud import create_item, get_item, get_item_by_id, get_items, update_item
from app.services.websockets import broadcast_server_event, broadcast_user_servers_event

logger = logging.getLogger(__name__)


async def create_user(user_model: UserCreateSchema) -> User:
    user_model.wallet_address = checksum_address(user_model.wallet_address)
    return await create_item(item=user_model, result_obj=User, user_field=None)


async def get_user_by_wallet_address(wallet_address: str) -> Union[User, APIDocument]:
    user = await get_item(filters={"wallet_address": wallet_address}, result_obj=User)
    return user


async def get_user_by_id(user_id) -> Union[User, APIDocument]:
    return await get_item_by_id(id_=user_id, result_obj=User)


async def get_user_profile_by_server_id(server_id: str, current_user: User) -> Union[ServerMember, APIDocument]:
    profile = await get_item(
        filters={"server": ObjectId(server_id), "user": current_user.pk},
        result_obj=ServerMember,
    )

    if not profile:
        raise HTTPException(status_code=http.HTTPStatus.NOT_FOUND)

    return profile


async def set_user_profile_picture(data: dict, current_user: User, profile: Union[ServerMember, User]) -> dict:
    pfp_input_string = data.get("pfp", "")
    if not pfp_input_string:
        return data

    pfp_data = {"input": pfp_input_string}

    contract_address, token_id = await extract_contract_and_token_from_string(pfp_input_string)
    if contract_address and token_id:
        owns_nft = await verify_token_ownership(
            contract_address=contract_address,
            token_id=token_id,
            wallet_address=current_user.wallet_address,
        )
        if owns_nft:
            logger.debug(f"{current_user.id} owns {contract_address}/{token_id}")
            token = await get_nft(contract_address=contract_address, token_id=token_id)
            image_url = await get_nft_image_url(token)
            logger.debug(f"{contract_address}/{token_id} image: {image_url}")

            pfp_data.update(
                {
                    "contract": contract_address,
                    "token_id": token_id,
                    "verified": True,
                    "input_image_url": image_url,
                    "token": token,
                }
            )
        else:
            logger.debug(f"{current_user.id} does not own {contract_address}/{token_id}")
            del [data["pfp"]]
            return data
    else:
        image_url = pfp_input_string
        if not pfp_input_string.startswith("http"):
            del [data["pfp"]]
            return data

        pfp_data["verified"] = False
        pfp_data["input_image_url"] = image_url

    if image_url.startswith("http"):
        metadata = {"user": str(current_user.pk), "profile": str(profile.pk)}
        await queue_bg_task(upload_pfp_url_and_update_profile, pfp_input_string, image_url, profile, metadata)
    else:
        logger.warning("image found is not a URL, ignoring upload to cloudflare for now")

    data["pfp"] = pfp_data
    return data


async def update_user_profile(
    server_id: Optional[str], update_data: Union[UserUpdateSchema, ServerMemberUpdateSchema], current_user: User
) -> Union[ServerMember, User]:
    data = update_data.dict(exclude_unset=True)

    if server_id:
        profile = await get_item(
            filters={"server": ObjectId(server_id), "user": current_user.pk},
            result_obj=ServerMember,
        )

        if not profile:
            raise HTTPException(status_code=http.HTTPStatus.NOT_FOUND)
    else:
        profile = current_user

    if "pfp" in data:
        if data["pfp"] != "":
            data = await set_user_profile_picture(data, current_user=current_user, profile=profile)
        else:
            data["pfp"] = None

    updated_item = await update_item(item=profile, data=data)

    if data:
        if server_id:
            await queue_bg_task(
                broadcast_server_event,
                server_id,
                str(current_user.id),
                WebSocketServerEvent.SERVER_PROFILE_UPDATE,
                {**data, "user": str(current_user.id), "member": str(profile.id)},
            )
        else:
            await queue_bg_task(
                broadcast_user_servers_event,
                str(current_user.id),
                WebSocketServerEvent.USER_PROFILE_UPDATE,
                {**data, "user": str(current_user.id)},
            )

    return updated_item


async def get_user_read_states(current_user: User):
    return await get_items(filters={"user": current_user.pk}, result_obj=ChannelReadState, limit=None)
