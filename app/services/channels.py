import http
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional, Union

from bson import ObjectId
from fastapi import HTTPException
from sentry_sdk import capture_exception
from starlette import status

from app.helpers.permissions import user_belongs_to_server
from app.helpers.queue_utils import queue_bg_task
from app.helpers.w3 import checksum_address
from app.helpers.ws_events import WebSocketServerEvent
from app.models.base import APIDocument
from app.models.channel import Channel, ChannelReadState
from app.models.message import Message
from app.models.section import Section
from app.models.server import ServerMember
from app.models.user import User
from app.schemas.channels import (
    ChannelBulkReadStateCreateSchema,
    ChannelReadStateCreateSchema,
    ChannelUpdateSchema,
    DMChannelCreateSchema,
    ServerChannelCreateSchema,
)
from app.schemas.users import UserCreateSchema
from app.services.crud import (
    create_item,
    delete_item,
    find_and_update_item,
    get_item,
    get_item_by_id,
    get_items,
    update_item,
)
from app.services.users import create_user, get_user_by_wallet_address
from app.services.websockets import broadcast_channel_event

logger = logging.getLogger(__name__)


async def create_dm_channel(channel_model: DMChannelCreateSchema, current_user: User) -> Union[Channel, APIDocument]:
    dm_users = []
    for member in channel_model.members:
        if re.match(r"^0x[a-fA-F\d]{40}$", member):
            wallet_addr = checksum_address(member)
            user = await get_user_by_wallet_address(wallet_address=wallet_addr)
            if not user:
                user = await create_user(user_model=UserCreateSchema(wallet_address=wallet_addr))
            dm_users.append(user.pk)
        else:
            dm_users.append(ObjectId(member))

    channel_model.members = list(set(dm_users))

    if current_user.pk not in channel_model.members:
        channel_model.members.insert(0, current_user.pk)

    # if same exact dm channel already exists, ignore
    filters = {
        "members": {
            "$size": len(channel_model.members),
            "$all": channel_model.members,
        },
    }
    existing_dm_channels = await get_items(filters=filters, result_obj=Channel)
    if existing_dm_channels:
        # TODO: return 200 status code
        return existing_dm_channels[0]

    return await create_item(channel_model, result_obj=Channel, current_user=current_user, user_field="owner")


async def create_server_channel(
    channel_model: ServerChannelCreateSchema, current_user: User
) -> Union[Channel, APIDocument]:
    return await create_item(channel_model, result_obj=Channel, current_user=current_user, user_field="owner")


async def create_channel(
    channel_model: Union[DMChannelCreateSchema, ServerChannelCreateSchema], current_user: User
) -> Union[Channel, APIDocument]:
    kind = channel_model.kind
    if isinstance(channel_model, DMChannelCreateSchema):
        return await create_dm_channel(channel_model, current_user)
    elif isinstance(channel_model, ServerChannelCreateSchema):
        return await create_server_channel(channel_model=channel_model, current_user=current_user)
    else:
        raise Exception(f"unexpected channel kind: {kind}")


async def get_server_channels(server_id, current_user: User) -> List[Union[Channel, APIDocument]]:
    if not await user_belongs_to_server(user=current_user, server_id=server_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing permissions")

    return await get_items(filters={"server": ObjectId(server_id)}, result_obj=Channel, limit=None)


async def get_dm_channels(current_user: User, limit: Optional[int] = None) -> List[Union[Channel, APIDocument]]:
    return await get_items(filters={"members": current_user.pk}, result_obj=Channel, limit=limit)


async def delete_channel(channel_id, current_user: User):
    channel = await get_item_by_id(id_=channel_id, result_obj=Channel)
    channel_owner = channel.owner
    is_channel_owner = channel_owner == current_user

    if channel.kind == "server":
        server = await channel.server.fetch()
        server_owner = server.owner
        if not is_channel_owner and not current_user == server_owner:
            raise HTTPException(status_code=http.HTTPStatus.FORBIDDEN)
    elif channel.kind == "dm":
        raise HTTPException(status_code=http.HTTPStatus.FORBIDDEN)
    else:
        raise Exception(f"unexpected kind of channel: {channel.kind}")

    deleted_channel = await delete_item(item=channel)

    try:
        section = await get_item(filters={"channels": ObjectId(channel_id)}, result_obj=Section)
        if section:
            section.channels.remove(channel)
            await section.commit()
    except Exception as e:
        logger.warning("trying to delete channel from section failed: %s", e)
        capture_exception(e)

    return deleted_channel


async def update_channel_last_message(channel_id, message: Union[Message, APIDocument], current_user: User):
    channel = await get_item_by_id(id_=channel_id, result_obj=Channel)
    if not channel.last_message_at or message.created_at > channel.last_message_at:
        await update_item(item=channel, data={"last_message_at": message.created_at})


async def bulk_mark_channels_as_read(ack_data: ChannelBulkReadStateCreateSchema, current_user: User):
    await update_channels_read_state(
        channel_ids=ack_data.channels, current_user=current_user, last_read_at=ack_data.last_read_at
    )


async def mark_channel_as_read(channel_id: str, last_read_at: Optional[datetime], current_user: User):
    await update_channels_read_state(channel_ids=[channel_id], current_user=current_user, last_read_at=last_read_at)


async def update_channels_read_state(channel_ids: List[str], current_user: User, last_read_at: Optional[datetime]):
    if not last_read_at:
        last_read_at = datetime.now(timezone.utc)

    for channel_id in channel_ids:
        # TODO: check if any mentions present after last_read_at. if so, change mention_count below
        update_data = {"$set": {"last_read_at": last_read_at, "mention_count": 0}}
        updated_item = await find_and_update_item(
            filters={"user": current_user.pk, "channel": ObjectId(channel_id)},
            data=update_data,
            result_obj=ChannelReadState,
        )

        if not updated_item:
            read_state_model = ChannelReadStateCreateSchema(channel=channel_id, last_read_at=last_read_at)
            await create_item(read_state_model, result_obj=ChannelReadState, current_user=current_user)


async def create_typing_indicator(channel_id: str, current_user: User) -> None:
    channel = await get_item_by_id(id_=channel_id, result_obj=Channel)
    notify = False

    if channel.kind == "server":
        user_member = await get_item(
            filters={"user": current_user, "server": channel.server.pk},
            result_obj=ServerMember,
        )
        notify = True if user_member else False
    elif channel.kind == "dm":
        notify = current_user in channel.members

    if notify:
        await queue_bg_task(
            broadcast_channel_event,
            channel_id,
            str(current_user.id),
            WebSocketServerEvent.USER_TYPING,
            {"user": await current_user.to_dict(exclude_fields=["pfp"])},
        )


async def update_channel(channel_id: str, update_data: ChannelUpdateSchema, current_user: User):
    channel = await get_item_by_id(id_=channel_id, result_obj=Channel)

    data = update_data.dict(exclude_unset=True)

    if channel.kind == "server":
        server = await channel.server.fetch()
        if channel.owner != current_user and server.owner != current_user:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User cannot change this channel")
    elif channel.kind == "dm":
        if current_user not in channel.members:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User cannot change this channel")
    else:
        raise Exception(f"unknown channel kind: {channel.kind}")

    updated_item = await update_item(item=channel, data=data)

    await queue_bg_task(
        broadcast_channel_event,
        channel_id,
        str(current_user.id),
        WebSocketServerEvent.CHANNEL_UPDATE,
        {"channel": channel_id},
    )

    return updated_item
