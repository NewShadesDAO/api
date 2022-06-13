import binascii
import secrets
from typing import Union

import arrow
import pytest
from asgi_lifespan import LifespanManager
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import FastAPI
from httpx import AsyncClient
from redis.asyncio.client import Redis
from web3 import Web3

from app.helpers import cloudflare
from app.helpers.cache_utils import cache
from app.helpers.connection import get_client, get_db
from app.helpers.jwt import generate_jwt_token
from app.main import get_application
from app.models.app import App
from app.models.auth import RefreshToken
from app.models.base import APIDocument
from app.models.channel import Channel
from app.models.server import Server
from app.models.user import User
from app.schemas.apps import AppCreateSchema
from app.schemas.auth import AuthWalletSchema, RefreshTokenCreateSchema
from app.schemas.channels import DMChannelCreateSchema, ServerChannelCreateSchema
from app.schemas.messages import MessageCreateSchema
from app.schemas.servers import ServerCreateSchema
from app.schemas.users import UserCreateSchema
from app.schemas.webhooks import WebhookCreateSchema
from app.services.apps import create_app, create_app_webhook
from app.services.auth import generate_wallet_token
from app.services.channels import create_dm_channel, create_server_channel
from app.services.crud import create_item
from app.services.messages import create_message
from app.services.servers import create_server
from app.services.users import create_user


@pytest.fixture
async def app() -> FastAPI:
    app = get_application(testing=True)
    return app


@pytest.fixture
async def client(app: FastAPI):
    async with LifespanManager(app):
        async with AsyncClient(app=app, base_url="http://testserver", follow_redirects=True) as client:
            yield client


@pytest.fixture(autouse=True)
async def redis(client):
    await cache.client.flushdb()
    yield cache.client
    await cache.client.flushdb()


@pytest.fixture
async def db(client):
    db_client = await get_client()
    db = await get_db()
    await db_client.drop_database(db.name)
    yield db
    await db_client.drop_database(db.name)


@pytest.fixture
def private_key() -> bytes:
    key = secrets.token_bytes(32)
    return key


@pytest.fixture
def wallet(private_key: bytes) -> str:
    priv = binascii.hexlify(private_key).decode("ascii")
    hex_private_key = "0x" + priv
    acct = Account.from_key(hex_private_key)
    return acct.address


@pytest.fixture
async def current_user(private_key: bytes, wallet: str) -> User:
    return await create_user(UserCreateSchema(wallet_address=wallet))


@pytest.fixture
async def guest_user() -> User:
    key = secrets.token_bytes(32)
    priv = binascii.hexlify(key).decode("ascii")
    private_key = "0x" + priv
    acct = Account.from_key(private_key)
    return await create_user(UserCreateSchema(wallet_address=acct.address))


@pytest.fixture
async def create_new_user():
    async def _create_new_user():
        key = secrets.token_bytes(32)
        priv = binascii.hexlify(key).decode("ascii")
        private_key = "0x" + priv
        acct = Account.from_key(private_key)
        return await create_user(UserCreateSchema(wallet_address=acct.address))

    return _create_new_user


@pytest.fixture
async def server(current_user: User) -> Union[Server, APIDocument]:
    server_model = ServerCreateSchema(name="NewShades DAO")
    return await create_server(server_model, current_user=current_user)


@pytest.fixture
async def server_channel(current_user: User, server: Server) -> Union[Channel, APIDocument]:
    server_channel = ServerChannelCreateSchema(kind="server", server=str(server.id), name="testing-channel")
    return await create_server_channel(channel_model=server_channel, current_user=current_user)


@pytest.fixture
async def dm_channel(current_user: User, server: Server) -> Union[Channel, APIDocument]:
    dm_channel = DMChannelCreateSchema(kind="dm", members=[str(current_user.id)])
    return await create_dm_channel(channel_model=dm_channel, current_user=current_user)


@pytest.fixture
async def channel_message(current_user: User, server: Server, server_channel: Channel):
    message = MessageCreateSchema(server=str(server.id), channel=str(server_channel.id), content="hey")
    return await create_message(message_model=message, current_user=current_user)


@pytest.fixture
async def direct_message(current_user: User, server: Server, dm_channel: Channel):
    message = MessageCreateSchema(channel=str(dm_channel.id), content="hey")
    return await create_message(message_model=message, current_user=current_user)


@pytest.fixture
async def integration_app(current_user: User):
    app_schema = AppCreateSchema(name="github", permissions=["messages.create"])
    return await create_app(model=app_schema, current_user=current_user)


@pytest.fixture
async def integration_app_webhook(current_user: User, integration_app: App, server_channel: Channel):
    schema = WebhookCreateSchema(channel=str(server_channel.pk))
    return await create_app_webhook(app_id=str(integration_app.pk), webhook_data=schema, current_user=current_user)


@pytest.fixture
async def authorized_client(client: AsyncClient, private_key: bytes, current_user: User):
    nonce = 1234
    signed_at = arrow.utcnow().isoformat()
    message = f"""NewShades wants you to sign in with your web3 account

    {current_user.wallet_address}

    URI: localhost
    Nonce: {nonce}
    Issued At: {signed_at}"""

    encoded_message = encode_defunct(text=message)
    signed_message = Web3().eth.account.sign_message(encoded_message, private_key=private_key)

    data = {
        "message": message,
        "signature": signed_message.signature.hex(),
        "signed_at": signed_at,
        "nonce": nonce,
        "address": current_user.wallet_address,
    }

    token = await generate_wallet_token(AuthWalletSchema(**data))
    access_token = token.access_token

    client.headers.update({"Authorization": f"Bearer {access_token}"})

    yield client
    client.headers.pop("Authorization")


@pytest.fixture
async def get_authorized_client(client: AsyncClient, redis: Redis):
    async def _get_authorized_client(user: User):
        access_token = generate_jwt_token(data={"sub": str(user.id)})
        refresh_token = generate_jwt_token(data={"sub": str(user.id)}, token_type="refresh")
        await create_item(
            RefreshTokenCreateSchema(refresh_token=refresh_token, user=str(user.id)),
            result_obj=RefreshToken,
            current_user=user,
        )
        await redis.sadd(f"refresh_tokens:{str(user.pk)}", refresh_token)
        client.headers.update({"Authorization": f"Bearer {access_token}"})
        return client

    return _get_authorized_client


@pytest.fixture(autouse=True)
async def mock_cloudflare_upload_image_url(monkeypatch):
    async def mock_upload_image_url(*args, **kwargs):
        return {"id": "7d5d3a42-22b0-4dff-ab43-1426264567a7"}

    monkeypatch.setattr(cloudflare, "upload_image_url", mock_upload_image_url)


@pytest.fixture
async def get_signed_message_data():
    async def _get_signed_message_data(private_key, address):
        nonce = 1234
        signed_at = arrow.utcnow().isoformat()
        message = f"""NewShades wants you to sign in with your web3 account

                    {address}

                    URI: localhost
                    Nonce: {nonce}
                    Issued At: {signed_at}"""

        encoded_message = encode_defunct(text=message)
        signed_message = Web3().eth.account.sign_message(encoded_message, private_key=private_key)

        data = {
            "message": message,
            "signature": signed_message.signature.hex(),
            "signed_at": signed_at,
            "nonce": nonce,
            "address": address,
        }

        return data

    return _get_signed_message_data
