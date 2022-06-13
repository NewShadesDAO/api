import ens
import pytest

from app.helpers.w3 import checksum_address
from app.models.user import User
from app.schemas.users import UserCreateSchema
from app.services.users import create_user, set_user_profile_picture


class TestUsersService:
    @pytest.mark.skip("No longer shortening wallet addresses")
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "wallet_address, expected_display_name",
        [
            ("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "0xd8d...045"),
            ("0x123A6BF26964aF9D7eEd9e03E53415D37aA96456", "0x123...456"),
        ],
    )
    async def test_create_user(self, db, wallet_address, expected_display_name):
        user_model = UserCreateSchema(wallet_address=wallet_address)
        user = await create_user(user_model=user_model)
        assert user is not None
        assert user.wallet_address == checksum_address(wallet_address)
        assert user.display_name == expected_display_name

    @pytest.mark.skip("No longer resolving ENS")
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "wallet_address, expected_display_name",
        [
            ("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "vitalik.eth"),
            ("0xd8da6bf26964af9d7eed9e03e53415d37aa96045", "vitalik.eth"),
            ("0x0000000000000000000000000000000000000000", "0x000...000"),
        ],
    )
    async def test_create_user_resolve_ens(self, db, wallet_address, expected_display_name, monkeypatch):
        user_model = UserCreateSchema(wallet_address=wallet_address)

        def mock_ens_name(cls, address):
            if address.lower() == "0xd8da6bf26964af9d7eed9e03e53415d37aa96045":
                return "vitalik.eth"
            else:
                return None

        monkeypatch.setattr(ens.ENS, "name", mock_ens_name)

        user = await create_user(user_model=user_model)
        assert user is not None
        assert user.wallet_address == checksum_address(wallet_address)
        assert user.display_name == expected_display_name

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "wallet_address",
        [
            "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96",
            "0xd8da6bf26964af9d7eed9e03e53415d37aa9604Z",
        ],
    )
    async def test_create_user_invalid_address(self, db, wallet_address):
        user_model = UserCreateSchema(wallet_address=wallet_address)
        with pytest.raises(ValueError):
            await create_user(user_model=user_model)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "input_str, wallet_address, verified",
        [
            (
                "https://opensea.io/assets/ethereum/0x58f7e9810f5559dc759b731843212370363e433e/449",
                "0x4977A4b74D3a81dB4c462d9073E10796d0cEE333",
                True,
            ),
            (
                "0x2605afbb22c59296c16ef5e477110357f760b20f 33",
                "0xa86882277e69fbf0a51805cdc8b0a3a113079e63",
                True,
            ),
            (
                "0x2605afbb22c59296c16ef5e477110357f760b20f 33",
                "0x4977A4b74D3a81dB4c462d9073E10796d0cEE333",
                False,
            ),
        ],
    )
    async def test_update_user_pfp_nft(self, db, input_str, wallet_address, verified):
        user_model = UserCreateSchema(wallet_address=wallet_address)
        user = await create_user(user_model=user_model)

        data = {"pfp": input_str}
        updated_data = await set_user_profile_picture(data, user, user)
        if verified:
            assert "pfp" in updated_data
            pfp_data = updated_data["pfp"]
            assert pfp_data["verified"] is True
        else:
            assert "pfp" not in updated_data

    @pytest.mark.asyncio
    async def test_update_user_pfp_image(self, db, current_user: User):
        data = {"pfp": "https://raw.githubusercontent.com/Ashwinvalento/cartoon-avatar/master/lib/images/female/5.png"}
        updated_data = await set_user_profile_picture(data, current_user, current_user)
        assert updated_data["pfp"] == data["pfp"]
        assert "verified" in updated_data["pfp"]
        assert updated_data["pfp"]["verified"] is False

    @pytest.mark.asyncio
    async def test_update_user_pfp_random(self, db, current_user: User):
        data = {"pfp": "asdfasdf"}
        updated_data = await set_user_profile_picture(data, current_user, current_user)
        assert "pfp" not in updated_data
