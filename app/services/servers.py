from typing import List, Union

from bson import ObjectId
from fastapi import HTTPException
from starlette import status

from app.models.base import APIDocument
from app.models.server import Server, ServerMember
from app.models.user import User
from app.schemas.servers import ServerCreateSchema
from app.services.crud import create_item, get_item, get_items


async def create_server(server_model: ServerCreateSchema, current_user: User) -> Union[Server, APIDocument]:
    created_server = await create_item(server_model, result_obj=Server, current_user=current_user, user_field="owner")

    # add owner as server member
    await join_server(created_server, current_user)

    return created_server


async def join_server(server: Union[Server, APIDocument], current_user: User) -> ServerMember:
    member = ServerMember(server=server, user=current_user)
    await member.commit()
    return member


async def get_user_servers(current_user: User) -> List[Server]:
    server_members = await get_items(
        {"user": current_user.id}, result_obj=ServerMember, current_user=current_user, size=None
    )
    return [await member.server.fetch() for member in server_members]


async def get_server_members(server_id: str, current_user: User):
    user_belongs_to_server = await get_item(
        filters={"server": ObjectId(server_id), "user": current_user.id},
        result_obj=ServerMember,
        current_user=current_user,
    )
    if not user_belongs_to_server:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing permissions")

    server_members = await get_items(
        {"server": ObjectId(server_id)}, result_obj=ServerMember, current_user=current_user, size=None
    )
    return server_members
