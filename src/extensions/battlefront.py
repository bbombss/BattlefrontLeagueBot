import hikari
import lightbulb

from src.models import (
    BattleFrontBot,
    BattlefrontBotPlugin,
    BattlefrontBotSlashContext,
    CapsRegisterView,
    GameSession,
    SessionContext,
)
from src.static import *
from src.utils import is_admin

battlefront = BattlefrontBotPlugin("battlefront")


# For testing
class Fakemember:
    """Fake member object used for testing."""

    def __init__(self, id, display_name, role_ids):
        self.id = id
        self.display_name = display_name
        self.role_ids = role_ids


def get_fake_members() -> list[Fakemember]:
    """Will returns a list of fake members for testing."""
    return [
        Fakemember(
            1,
            "fake1",
            [
                1384163685542531204,
            ],
        ),
        Fakemember(
            2,
            "fake2",
            [
                1384163837699297321,
            ],
        ),
        Fakemember(
            3,
            "fake3",
            [
                1384163685542531204,
            ],
        ),
        Fakemember(
            4,
            "fake4",
            [
                1384163685542531204,
            ],
        ),
        Fakemember(
            5,
            "fake5",
            [
                1384163837699297321,
            ],
        ),
        Fakemember(
            6,
            "fake6",
            [
                1384163837699297321,
            ],
        ),
        Fakemember(
            7,
            "fake7",
            [
                1384163904967675914,
            ],
        ),
        Fakemember(
            8,
            "fake8",
            [
                1384163904967675914,
            ],
        ),
    ]


@battlefront.command
@lightbulb.option("greencaps", "The role for green caps.", type=hikari.Role, required=True)
@lightbulb.option("yellowcaps", "The role for yellow caps.", type=hikari.Role, required=True)
@lightbulb.option("redcaps", "The role for red caps.", type=hikari.Role, required=True)
@lightbulb.command("setroles", description="Set the roles that determine player rank.", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def set_roles(
    ctx: BattlefrontBotSlashContext, greencaps: hikari.Role, yellowcaps: hikari.Role, redcaps: hikari.Role
) -> None:
    if not is_admin(ctx.member):
        await ctx.respond_with_failure("**Only administrators can set roles**", ephemeral=True)
        return

    await ctx.wait()

    await ctx.app.db.execute(
        """
        UPDATE guilds
        SET rank1Role = $1, rank2Role = $2, rank3Role = $3
        WHERE guildId = $4
        """,
        greencaps.id,
        yellowcaps.id,
        redcaps.id,
        ctx.guild_id,
    )

    await ctx.respond_with_success("**Successfully updated rank roles**", edit=True)


@battlefront.command
@lightbulb.option("timeout", "How long the bot should wait for 8 players", type=int, required=False)
@lightbulb.command("startcaps", description="Starts caps.", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def bot_info(ctx: BattlefrontBotSlashContext, timeout: int = 600) -> None:
    record = await ctx.app.db.fetchrow("SELECT * FROM guilds WHERE guildId = $1", ctx.guild_id)
    assert record is not None
    if record["rank1role"] is None or record["rank2role"] is None or record["rank3role"] is None:
        await ctx.respond_with_failure(
            "Could not find rank roles for server, use `/setroles` to configure rank roles", ephemeral=True
        )
        return

    embed = hikari.Embed(
        description=f"**{ctx.author.display_name} has started matchmaking for Caps.\n"
        f"Register your interest below** :point_down:",
        colour=DEFAULT_EMBED_COLOUR,
    )
    embed.set_footer("Waiting for players...")

    view = CapsRegisterView(timeout=timeout)

    message = await ctx.respond(embed=embed, components=view)

    ctx.app.miru_client.start_view(view, bind_to=message)
    await view.wait()

    if len(view.registered_members) < 8:
        await message.edit(
            embed=hikari.Embed(description=f"{FAIL_EMOJI} **Not enough players registered**", colour=FAIL_EMBED_COLOUR),
            components=[],
        )
        return

    embed = hikari.Embed(description=f"{SUCCESS_EMOJI} **Registration complete**", colour=DEFAULT_EMBED_COLOUR)
    embed.add_field(name="Participants:", value="\n".join([user.display_name for user in view.registered_members]))
    embed.set_footer("Starting session...")

    await message.edit(embed=embed, components=[])

    game_context = SessionContext(ctx.app, ctx.get_guild(), ctx.get_channel(), ctx.member)
    session = GameSession(game_context)

    embed.set_footer(f"Session: {ctx.app.game_session_manager.session_count + 1}")
    await message.edit(embed=embed)

    await session.start(view.registered_members)


def load(bot: BattleFrontBot) -> None:
    bot.add_plugin(battlefront)


def unload(bot: BattleFrontBot) -> None:
    bot.remove_plugin(battlefront)


# Copyright (C) 2025 BBombs

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
