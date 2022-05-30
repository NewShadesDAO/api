import http
from datetime import datetime
from typing import List, Optional, Union

from fastapi import APIRouter, Body, Depends

from app.dependencies import common_parameters, get_current_user
from app.models.user import User
from app.schemas.channels import (
    ChannelBulkReadStateCreateSchema,
    ChannelUpdateSchema,
    DMChannelCreateSchema,
    EitherChannel,
    ServerChannelCreateSchema,
    URLChannelCreateSchema,
)
from app.schemas.messages import MessageSchema
from app.services.channels import (
    bulk_mark_channels_as_read,
    create_channel,
    create_typing_indicator,
    delete_channel,
    mark_channel_as_read,
    update_channel,
)
from app.services.messages import get_message, get_messages

router = APIRouter()


@router.post(
    "",
    response_description="Create new channel",
    response_model=EitherChannel,
    status_code=http.HTTPStatus.CREATED,
)
async def post_create_channel(
    channel: Union[URLChannelCreateSchema, DMChannelCreateSchema, ServerChannelCreateSchema] = Body(...),
    current_user: User = Depends(get_current_user),
):
    return await create_channel(channel, current_user=current_user)


@router.get("/{channel_id}/messages", response_description="Get latest messages", response_model=List[MessageSchema])
async def get_list_messages(
    channel_id,
    common_params: dict = Depends(common_parameters),
    current_user: User = Depends(get_current_user),
):
    messages = await get_messages(channel_id=channel_id, current_user=current_user, **common_params)
    return messages


@router.get("/{channel_id}/messages/{message_id}", response_description="Get message", response_model=MessageSchema)
async def get_specific_message(channel_id, message_id, current_user: User = Depends(get_current_user)):
    return await get_message(channel_id=channel_id, message_id=message_id, current_user=current_user)


@router.delete("/{channel_id}", response_description="Delete channel", response_model=EitherChannel)
async def delete_remove_channel(channel_id, current_user: User = Depends(get_current_user)):
    return await delete_channel(channel_id=channel_id, current_user=current_user)


@router.post("/{channel_id}/typing", summary="Notify typing", status_code=http.HTTPStatus.NO_CONTENT)
async def post_user_typing_in_channel(channel_id, current_user: User = Depends(get_current_user)):
    await create_typing_indicator(channel_id, current_user)


@router.patch("/{channel_id}", summary="Update channel", response_model=EitherChannel, status_code=http.HTTPStatus.OK)
async def patch_update_channel(
    channel_id,
    update_data: ChannelUpdateSchema,
    current_user: User = Depends(get_current_user),
):
    return await update_channel(channel_id, update_data=update_data, current_user=current_user)


@router.post("/{channel_id}/ack", response_description="ACK channel", status_code=http.HTTPStatus.NO_CONTENT)
async def post_mark_channel_read(
    channel_id, last_read_at: Optional[datetime] = None, current_user: User = Depends(get_current_user)
):
    await mark_channel_as_read(channel_id, last_read_at, current_user=current_user)


@router.post("/ack", response_description="Bulk ACK channels", status_code=http.HTTPStatus.NO_CONTENT)
async def post_bulk_mark_channels_read(
    ack_data: ChannelBulkReadStateCreateSchema, current_user: User = Depends(get_current_user)
):
    await bulk_mark_channels_as_read(ack_data, current_user=current_user)
