import binascii
import datetime
import secrets
from typing import Callable

import arrow
import pytest
from eth_account import Account
from fastapi import FastAPI
from httpx import AsyncClient
from pymongo.database import Database

from app.models.channel import Channel
from app.models.server import Server
from app.models.user import User
from app.schemas.channels import ServerChannelCreateSchema
from app.schemas.messages import MessageCreateSchema
from app.schemas.servers import ServerCreateSchema
from app.services.channels import create_server_channel, get_dm_channels
from app.services.crud import create_item
from app.services.messages import create_message
from app.services.servers import create_server, get_user_servers
from app.services.users import get_user_by_id, get_user_by_wallet_address


class TestChannelsRoutes:
    @pytest.mark.asyncio
    async def test_create_dm_channel(
        self, app: FastAPI, db: Database, current_user: User, authorized_client: AsyncClient
    ):
        members = []
        for x in range(3):
            user = User(wallet_address=f"0x{x}")
            await user.commit()
            members.append(user)

        data = {"kind": "dm", "members": [str(member.id) for member in members]}

        response = await authorized_client.post("/channels", json=data)
        assert response.status_code == 201
        json_response = response.json()
        assert json_response != {}
        assert "kind" in json_response
        assert json_response["kind"] == data["kind"]
        assert "owner" in json_response
        assert json_response["owner"] == str(current_user.id)
        assert "members" in json_response
        assert all([member in json_response["members"] for member in data["members"]])
        assert str(current_user.id) in json_response["members"]

    @pytest.mark.asyncio
    async def test_create_personal_dm_channel(
        self, app: FastAPI, db: Database, current_user: User, authorized_client: AsyncClient
    ):
        data = {"kind": "dm", "members": []}

        response = await authorized_client.post("/channels", json=data)
        assert response.status_code == 201
        json_response = response.json()
        assert json_response != {}
        assert "kind" in json_response
        assert json_response["kind"] == data["kind"]
        assert "owner" in json_response
        assert json_response["owner"] == str(current_user.id)
        assert "members" in json_response
        assert str(current_user.id) in json_response["members"]

    @pytest.mark.asyncio
    async def test_create_multiple_personal_dm_channels(
        self, app: FastAPI, db: Database, current_user: User, authorized_client: AsyncClient
    ):
        data = {"kind": "dm", "members": []}

        response = await authorized_client.post("/channels", json=data)
        assert response.status_code == 201
        json_response = response.json()
        assert json_response != {}
        assert "kind" in json_response
        assert json_response["kind"] == data["kind"]
        assert "owner" in json_response
        assert json_response["owner"] == str(current_user.id)
        assert "members" in json_response
        assert str(current_user.id) in json_response["members"]
        channel_id = json_response["id"]

        response = await authorized_client.post("/channels", json=data)
        assert response.status_code == 201
        json_response = response.json()
        assert json_response["id"] == channel_id

    @pytest.mark.asyncio
    async def test_create_server_channel(
        self, app: FastAPI, db: Database, current_user: User, server: Server, authorized_client: AsyncClient
    ):
        data = {
            "kind": "server",
            "name": "fancy-announcements",
            "server": str(server.id),
        }

        response = await authorized_client.post("/channels", json=data)
        assert response.status_code == 201
        json_response = response.json()
        assert json_response != {}
        assert "kind" in json_response
        assert json_response["kind"] == data["kind"]
        assert "owner" in json_response
        assert json_response["owner"] == str(current_user.id)
        assert "name" in json_response
        assert json_response["name"] == data["name"]
        assert "server" in json_response
        assert json_response["server"] == str(server.id)

    @pytest.mark.asyncio
    async def test_create_server_channel_not_belong_to_server(
        self,
        app: FastAPI,
        db: Database,
        current_user: User,
        server: Server,
        authorized_client: AsyncClient,
        create_new_user: Callable,
        get_authorized_client: Callable,
    ):
        data = {
            "kind": "server",
            "name": "fancy-announcements",
            "server": str(server.id),
        }
        member = await create_new_user()
        member_auth_client = await get_authorized_client(member)

        response = await member_auth_client.post("/channels", json=data)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_server_channel_not_owner(
        self,
        app: FastAPI,
        db: Database,
        current_user: User,
        server: Server,
        authorized_client: AsyncClient,
        create_new_user: Callable,
        get_authorized_client: Callable,
    ):
        data = {
            "kind": "server",
            "name": "fancy-announcements",
            "server": str(server.id),
        }
        member = await create_new_user()
        member_auth_client = await get_authorized_client(member)

        response = await member_auth_client.post(f"/servers/{str(server.pk)}/join")
        assert response.status_code == 201

        response = await member_auth_client.post("/channels", json=data)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_server_channel_with_emojis(
        self, app: FastAPI, db: Database, current_user: User, server: Server, authorized_client: AsyncClient
    ):
        data = {
            "kind": "server",
            "name": "📣-fancy-announcements",
            "server": str(server.id),
        }

        response = await authorized_client.post("/channels", json=data)
        assert response.status_code == 201
        json_response = response.json()
        assert json_response != {}
        assert "kind" in json_response
        assert json_response["kind"] == data["kind"]
        assert "owner" in json_response
        assert json_response["owner"] == str(current_user.id)
        assert "name" in json_response
        assert json_response["name"] == data["name"]
        assert "server" in json_response
        assert json_response["server"] == str(server.id)

    @pytest.mark.asyncio
    async def test_delete_channel_ok(
        self, app: FastAPI, db: Database, authorized_client: AsyncClient, server: Server, server_channel: Channel
    ):
        response = await authorized_client.delete(f"/channels/{str(server_channel.id)}")
        assert response.status_code == 200
        json_response = response.json()
        assert json_response["id"] == str(server_channel.id)
        assert json_response["name"] == server_channel.name
        assert json_response["server"] == str(server.id)
        assert json_response["deleted"] is True

    @pytest.mark.asyncio
    async def test_delete_dm_channel(
        self, app: FastAPI, db: Database, authorized_client: AsyncClient, server: Server, dm_channel: Channel
    ):
        response = await authorized_client.delete(f"/channels/{str(dm_channel.id)}")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_channel_no_permission(
        self,
        app: FastAPI,
        db: Database,
        authorized_client: AsyncClient,
        current_user: User,
        server: Server,
        guest_user: User,
    ):
        server = await create_server(ServerCreateSchema(name="test Server"), current_user=guest_user)
        new_channel = Channel(server=server.id, owner=guest_user.id, kind="server")
        await new_channel.commit()

        response = await authorized_client.delete(f"/channels/{str(new_channel.id)}")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_server_channel_ok(
        self,
        app: FastAPI,
        db: Database,
        authorized_client: AsyncClient,
        current_user: User,
        server: Server,
        server_channel: Channel,
    ):
        data = {"name": "my-channel!"}
        response = await authorized_client.patch(f"/channels/{str(server_channel.pk)}", json=data)
        assert response.status_code == 200
        json_response = response.json()
        assert json_response["name"] == data["name"]

    @pytest.mark.asyncio
    async def test_update_dm_channel_ok(
        self,
        app: FastAPI,
        db: Database,
        authorized_client: AsyncClient,
        current_user: User,
        server: Server,
        dm_channel: Channel,
    ):
        data = {"name": "kool & the gang"}
        response = await authorized_client.patch(f"/channels/{str(dm_channel.pk)}", json=data)
        assert response.status_code == 200
        json_response = response.json()
        assert json_response["name"] == data["name"]

    @pytest.mark.asyncio
    async def test_update_server_channel_as_guest_fails(
        self,
        app: FastAPI,
        db: Database,
        authorized_client: AsyncClient,
        current_user: User,
        server: Server,
        server_channel: Channel,
        create_new_user: Callable,
        get_authorized_client: Callable,
    ):
        member = await create_new_user()
        member_auth_client = await get_authorized_client(member)

        data = {"name": "my-channel!"}
        response = await member_auth_client.patch(f"/channels/{str(server_channel.pk)}", json=data)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_dm_channel_as_non_member_fails(
        self,
        app: FastAPI,
        db: Database,
        authorized_client: AsyncClient,
        current_user: User,
        server: Server,
        dm_channel: Channel,
        create_new_user: Callable,
        get_authorized_client: Callable,
    ):
        member = await create_new_user()
        member_auth_client = await get_authorized_client(member)

        data = {"name": "my-channel!"}
        response = await member_auth_client.patch(f"/channels/{str(dm_channel.pk)}", json=data)
        assert response.status_code == 403

    @pytest.mark.skip
    @pytest.mark.asyncio
    async def test_update_dm_channel_remove_member_as_not_owner(
        self,
        app: FastAPI,
        db: Database,
        authorized_client: AsyncClient,
        current_user: User,
        create_new_user: Callable,
        get_authorized_client: Callable,
    ):
        guest = await create_new_user()
        guest_client = await get_authorized_client(guest)

        members = [current_user, guest]
        data = {"kind": "dm", "members": [str(member.id) for member in members]}

        response = await authorized_client.post("/channels", json=data)
        assert response.status_code == 201
        channel_id = response.json().get("id")

        data = {"members": [str(guest.id)]}
        response = await guest_client.patch(f"/channels/{channel_id}", json=data)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_mark_channel_as_read(
        self,
        app: FastAPI,
        db: Database,
        authorized_client: AsyncClient,
        current_user: User,
        server: Server,
        server_channel: Channel,
    ):
        response = await authorized_client.get("/users/me/read_states")
        assert response.status_code == 200
        json_response = response.json()
        assert len(json_response) == 0

        response = await authorized_client.post(f"/channels/{str(server_channel.pk)}/ack")
        assert response.status_code == 204

        response = await authorized_client.get("/users/me/read_states")
        assert response.status_code == 200
        json_response = response.json()
        assert len(json_response) == 1
        last_read_at = json_response[0]["last_read_at"]
        diff = arrow.utcnow() - arrow.get(last_read_at)
        assert diff.total_seconds() <= 1

    @pytest.mark.asyncio
    async def test_mark_channel_as_read_specific_ts(
        self,
        app: FastAPI,
        db: Database,
        authorized_client: AsyncClient,
        current_user: User,
        server: Server,
        server_channel: Channel,
    ):
        response = await authorized_client.get("/users/me/read_states")
        assert response.status_code == 200
        json_response = response.json()
        assert len(json_response) == 0

        mark_read_at = datetime.datetime.utcnow() - datetime.timedelta(seconds=10)
        response = await authorized_client.post(
            f"/channels/{str(server_channel.pk)}/ack?last_read_at={mark_read_at.isoformat()}"
        )
        assert response.status_code == 204

        response = await authorized_client.get("/users/me/read_states")
        assert response.status_code == 200
        json_response = response.json()
        assert len(json_response) == 1
        last_read_at = json_response[0]["last_read_at"]
        assert arrow.get(last_read_at).timestamp() == pytest.approx(mark_read_at.timestamp(), 0.001)

    @pytest.mark.asyncio
    async def test_bulk_mark_channels_as_read(
        self,
        app: FastAPI,
        db: Database,
        authorized_client: AsyncClient,
        current_user: User,
        server: Server,
        server_channel: Channel,
    ):
        response = await authorized_client.get("/users/me/read_states")
        assert response.status_code == 200
        json_response = response.json()
        assert len(json_response) == 0

        data = {"channels": [str(server_channel.pk)]}
        response = await authorized_client.post("/channels/ack", json=data)
        assert response.status_code == 204

        response = await authorized_client.get("/users/me/read_states")
        assert response.status_code == 200
        json_response = response.json()
        assert len(json_response) == 1
        last_read_at = json_response[0]["last_read_at"]
        diff = arrow.utcnow() - arrow.get(last_read_at)
        assert diff.total_seconds() <= 1

    @pytest.mark.asyncio
    async def test_bulk_mark_channels_as_read_specific_ts(
        self,
        app: FastAPI,
        db: Database,
        authorized_client: AsyncClient,
        current_user: User,
        server: Server,
        server_channel: Channel,
    ):
        response = await authorized_client.get("/users/me/read_states")
        assert response.status_code == 200
        json_response = response.json()
        assert len(json_response) == 0

        mark_read_at = datetime.datetime.utcnow() - datetime.timedelta(seconds=10)
        data = {"channels": [str(server_channel.pk)], "last_read_at": mark_read_at.isoformat()}
        response = await authorized_client.post("/channels/ack", json=data)
        assert response.status_code == 204

        response = await authorized_client.get("/users/me/read_states")
        assert response.status_code == 200
        json_response = response.json()
        assert len(json_response) == 1
        last_read_at = json_response[0]["last_read_at"]
        assert arrow.get(last_read_at).timestamp() == pytest.approx(mark_read_at.timestamp(), 0.001)

    @pytest.mark.asyncio
    async def test_bulk_mark_multiple_channels_as_read(
        self,
        app: FastAPI,
        db: Database,
        authorized_client: AsyncClient,
        current_user: User,
        server: Server,
    ):
        no_channels = 5
        channels = []
        for index, _ in enumerate(range(no_channels)):
            channel_schema = ServerChannelCreateSchema(server=str(server.pk), name=f"random-{index}")
            channel = await create_item(
                item=channel_schema, result_obj=Channel, current_user=current_user, user_field="owner"
            )
            channels.append(channel)

        response = await authorized_client.get("/users/me/read_states")
        assert response.status_code == 200
        json_response = response.json()
        assert len(json_response) == 0

        data = {"channels": [str(channel.pk) for channel in channels]}
        response = await authorized_client.post("/channels/ack", json=data)
        assert response.status_code == 204

        response = await authorized_client.get("/users/me/read_states")
        assert response.status_code == 200
        json_response = response.json()
        assert len(json_response) == no_channels
        now = arrow.utcnow()
        default_ts = None
        for read_state in json_response:
            last_read_at = read_state["last_read_at"]
            diff = now - arrow.get(last_read_at)
            assert diff.total_seconds() <= 1
            if default_ts:
                assert last_read_at == default_ts
            else:
                default_ts = last_read_at

    @pytest.mark.asyncio
    async def test_fetch_channel_messages(
        self,
        app: FastAPI,
        db: Database,
        current_user: User,
        authorized_client: AsyncClient,
        server: Server,
    ):
        channel1_model = ServerChannelCreateSchema(kind="server", server=str(server.id), name="channel1")
        channel1 = await create_server_channel(channel_model=channel1_model, current_user=current_user)

        channel2_model = ServerChannelCreateSchema(kind="server", server=str(server.id), name="channel2")
        channel2 = await create_server_channel(channel_model=channel2_model, current_user=current_user)

        channel1_msgs = []
        channel1_len = 3
        for _ in range(channel1_len):
            message_model = MessageCreateSchema(server=str(server.id), channel=str(channel1.pk), content="hey")
            message = await create_message(message_model=message_model, current_user=current_user)
            channel1_msgs.append(message)
        channel1_msgs_ids = [str(msg.pk) for msg in channel1_msgs]

        channel2_msgs = []
        channel2_len = 1
        for _ in range(channel2_len):
            message_model = MessageCreateSchema(server=str(server.id), channel=str(channel2.pk), content="hey")
            message = await create_message(message_model=message_model, current_user=current_user)
            channel2_msgs.append(message)
        channel2_msgs_ids = [str(msg.pk) for msg in channel2_msgs]

        response = await authorized_client.get(f"/channels/{str(channel1.pk)}/messages")
        assert response.status_code == 200
        json_response = response.json()
        assert len(response.json()) == channel1_len
        resp_channels = [msg.get("channel") for msg in json_response]
        assert all([channel_id == str(channel1.pk) for channel_id in resp_channels])
        assert all([msg.get("id") in channel1_msgs_ids for msg in json_response])

        response = await authorized_client.get(f"/channels/{str(channel2.pk)}/messages")
        assert response.status_code == 200
        json_response = response.json()
        assert len(response.json()) == channel2_len
        resp_channels = [msg.get("channel") for msg in json_response]
        assert all([channel_id == str(channel2.pk) for channel_id in resp_channels])
        assert all([msg.get("id") in channel2_msgs_ids for msg in json_response])

    @pytest.mark.asyncio
    async def test_create_dm_channel_with_wallets(
        self, app: FastAPI, db: Database, current_user: User, authorized_client: AsyncClient
    ):
        wallets = [current_user.wallet_address]
        for x in range(3):
            key = secrets.token_bytes(32)
            priv = binascii.hexlify(key).decode("ascii")
            private_key = "0x" + priv
            acct = Account.from_key(private_key)
            wallets.append(acct.address)

        data = {"kind": "dm", "members": wallets}

        response = await authorized_client.post("/channels", json=data)
        assert response.status_code == 201
        json_response = response.json()
        assert json_response != {}
        assert "kind" in json_response
        assert json_response["kind"] == data["kind"]
        assert "owner" in json_response
        assert json_response["owner"] == str(current_user.id)
        assert "members" in json_response
        assert str(current_user.id) in json_response["members"]
        for user_id in json_response["members"]:
            user = await get_user_by_id(user_id=user_id)
            assert user.wallet_address in data["members"]

    @pytest.mark.asyncio
    async def test_create_dm_channel_with_wallets_mix(
        self, app: FastAPI, db: Database, current_user: User, authorized_client: AsyncClient
    ):
        members = []
        for x in range(2):
            key = secrets.token_bytes(32)
            priv = binascii.hexlify(key).decode("ascii")
            private_key = "0x" + priv
            acct = Account.from_key(private_key)
            members.append(acct.address)

        for x in range(3):
            user = User(wallet_address=f"0x{x}")
            await user.commit()
            members.append(str(user.pk))

        data = {"kind": "dm", "members": members}

        response = await authorized_client.post("/channels", json=data)
        assert response.status_code == 201
        json_response = response.json()
        assert json_response != {}
        assert "kind" in json_response
        assert json_response["kind"] == data["kind"]
        assert "owner" in json_response
        assert json_response["owner"] == str(current_user.id)
        assert "members" in json_response
        assert len(json_response["members"]) == len(members) + 1
        assert str(current_user.id) in json_response["members"]
        for user_id in json_response["members"][1:]:
            user = await get_user_by_id(user_id=user_id)
            assert user.wallet_address in data["members"] or str(user.pk) in data["members"]

    @pytest.mark.asyncio
    async def test_create_dm_with_wallet_shows_on_signup(
        self,
        app: FastAPI,
        db: Database,
        current_user: User,
        server: Server,
        client: AsyncClient,
        authorized_client: AsyncClient,
        create_new_user: Callable,
        get_authorized_client: Callable,
        get_signed_message_data: Callable,
    ):
        key = secrets.token_bytes(32)
        priv = binascii.hexlify(key).decode("ascii")
        private_key = "0x" + priv
        acct = Account.from_key(private_key)
        new_user_wallet_addr = acct.address

        members = [str(current_user.pk), new_user_wallet_addr]
        data = {"kind": "dm", "members": members}

        # create DM with non-user address
        response = await authorized_client.post("/channels", json=data)
        assert response.status_code == 201
        json_response = response.json()
        assert json_response != {}
        assert "kind" in json_response
        assert json_response["kind"] == "dm"
        assert len(json_response.get("members")) == 2

        guest_user = await get_user_by_wallet_address(wallet_address=new_user_wallet_addr)
        assert guest_user is not None

        dm_channels = await get_dm_channels(current_user=guest_user)
        assert len(dm_channels) == 1

        user_servers = await get_user_servers(current_user=guest_user)
        assert len(user_servers) == 0

        data = await get_signed_message_data(private_key, new_user_wallet_addr)
        response = await client.post("/auth/login", json=data)
        assert response.status_code == 201

        user_servers = await get_user_servers(current_user=guest_user)
        assert len(user_servers) == 1
