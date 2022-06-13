import pytest

from app.helpers.guild_xyz import get_guild_member_roles, is_user_eligible_for_guild
from app.schemas.users import UserCreateSchema
from app.services.users import create_user


class TestGuildXYZUtils:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "wallet_address, guild_id",
        [
            ("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "1985"),  # Our Guild (guild.xyz)
        ],
    )
    async def test_user_is_eligible_for_guild_ok(self, db, wallet_address, guild_id):
        user_model = UserCreateSchema(wallet_address=wallet_address)
        user = await create_user(user_model=user_model)
        assert await is_user_eligible_for_guild(user, guild_id) is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "wallet_address, guild_id",
        [
            ("0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "2813"),  # NewShades Test Guild
        ],
    )
    async def test_user_is_eligible_for_guild_nok(self, db, wallet_address, guild_id):
        user_model = UserCreateSchema(wallet_address=wallet_address)
        user = await create_user(user_model=user_model)
        assert await is_user_eligible_for_guild(user, guild_id) is False

    @pytest.mark.asyncio
    async def test_get_roles_for_guild(self):
        addr = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"

        # every address has access to a default role in this guild
        guild_id = "1985"

        roles = await get_guild_member_roles(guild_id=guild_id, member_wallet_addr=addr)
        assert len(roles) == 1
        role = roles[0]
        assert role["access"] is True
        assert role["roleId"] == 1904
