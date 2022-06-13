import logging
import re

import arrow
from fastapi import HTTPException
from jose import JWTError
from starlette import status

from app.helpers.cache_utils import cache
from app.helpers.jwt import decode_jwt_token, generate_jwt_token
from app.helpers.w3 import checksum_address, get_wallet_address_from_signed_message
from app.models.auth import RefreshToken
from app.models.server import Server
from app.models.user import User
from app.schemas.auth import AccessTokenSchema, AuthWalletSchema, RefreshTokenCreateSchema
from app.schemas.users import UserCreateSchema
from app.services.crud import create_item, delete_items, get_item, get_items, update_item
from app.services.servers import get_user_servers, join_server
from app.services.users import create_user, get_user_by_id, get_user_by_wallet_address

logger = logging.getLogger(__name__)

SIGNATURE_VALID_SECONDS = 60
NONCE_SIGNATURE_REGEX = re.compile(r"nonce:\s?(.+?)\b", flags=re.IGNORECASE)
SIGNED_AT_SIGNATURE_REGEX = re.compile(r"issued at:\s?(.+?)$", flags=re.IGNORECASE)


async def add_user_to_default_server(user_id):
    user = await get_user_by_id(user_id=user_id)
    servers = await get_items(filters={}, result_obj=Server, sort_by_direction=1, limit=1)
    if not len(servers):
        logger.warning("no servers exist, ignoring default join!")
        return

    server = servers[0]
    await join_server(server_id=str(server.pk), current_user=user)


async def generate_wallet_token(data: AuthWalletSchema) -> AccessTokenSchema:
    message = data.message
    signature = data.signature

    if not message or not signature:
        raise Exception("missing params")

    address = data.address
    signed_at = arrow.get(data.signed_at)
    nonce = data.nonce

    try:
        signed_address = get_wallet_address_from_signed_message(message, signature)
    except Exception as e:
        raise e

    assert signed_address == checksum_address(address)
    assert signed_address.lower() in message.lower()

    signed_at_groups = re.search(SIGNED_AT_SIGNATURE_REGEX, message)
    if not signed_at_groups:
        raise AssertionError("signed_at not found")
    message_signed_at_str = signed_at_groups.group(1)
    message_signed_at = arrow.get(message_signed_at_str)
    assert signed_at == message_signed_at

    if signed_at <= arrow.utcnow().shift(seconds=-SIGNATURE_VALID_SECONDS):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="signature_expired")

    # check nonce
    nonce_groups = re.search(NONCE_SIGNATURE_REGEX, message)
    if not nonce_groups:
        raise AssertionError("nonce not found")
    message_nonce = nonce_groups.group(1)
    assert int(message_nonce) == nonce

    user = await get_user_by_wallet_address(wallet_address=signed_address)
    if not user:
        user = await create_user(UserCreateSchema(wallet_address=signed_address))

    servers = await get_user_servers(current_user=user)
    if not servers:
        # TODO: delete this once things are live
        await add_user_to_default_server(str(user.id))

    access_token = generate_jwt_token({"sub": str(user.id)})
    refresh_token = generate_jwt_token({"sub": str(user.id)}, token_type="refresh")
    await cache.client.sadd(f"refresh_tokens:{str(user.pk)}", refresh_token)

    await create_item(
        RefreshTokenCreateSchema(refresh_token=refresh_token, user=str(user.id)),
        result_obj=RefreshToken,
        current_user=user,
    )

    token = AccessTokenSchema(access_token=access_token, refresh_token=refresh_token)
    return token


async def create_refresh_token(token_model: RefreshTokenCreateSchema) -> AccessTokenSchema:
    refresh_token = await get_item(
        filters={"refresh_token": token_model.refresh_token},
        result_obj=RefreshToken,
    )

    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not find refresh token")

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_jwt_token(token_model.refresh_token)
        user_id: str = payload.get("sub")
        if not user_id:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    except Exception:
        logger.exception("Problems decoding refresh token. [jwt=%s]", token_model.refresh_token)
        raise credentials_exception

    user = await get_user_by_id(user_id=user_id)
    if not user:
        logger.warning("User in refresh token not found. [user_id=%s]", user_id)
        raise credentials_exception

    if refresh_token.used is True:
        logger.warning("tried to reuse already used refresh token. revoking all!")
        await delete_items(filters={"user": user.pk}, result_obj=RefreshToken)
        await cache.client.delete(f"refresh_tokens:{str(user.pk)}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token already used")
    else:
        await update_item(refresh_token, data={"used": True})

    access_token = generate_jwt_token({"sub": str(user.id)})
    refresh_token = generate_jwt_token({"sub": str(user.id)}, token_type="refresh")
    await cache.client.sadd(f"refresh_tokens:{str(user.pk)}", refresh_token)

    await create_item(
        RefreshTokenCreateSchema(refresh_token=refresh_token, user=str(user.id)),
        result_obj=RefreshToken,
        current_user=user,
    )

    token = AccessTokenSchema(access_token=access_token, refresh_token=refresh_token)
    return token


async def revoke_tokens(current_user: User):
    await cache.client.delete(f"refresh_tokens:{str(current_user.pk)}")
    await delete_items(filters={"user": current_user.pk}, result_obj=RefreshToken)
