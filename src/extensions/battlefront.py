import hikari
import lightbulb

from src.models import (
    BattleFrontBot,
    BattlefrontBotPlugin,
    BattlefrontBotSlashContext,
    CapsRegisterView,
    GameSession,
    GameContext
)
from src.static import *

battlefront = BattlefrontBotPlugin("battlefront")


# ToDo: Auth
@battlefront.command
@lightbulb.option("timeout", "How long the bot should wait for 8 players", type=int, required=False)
@lightbulb.command("startcaps", description="Starts caps.", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def bot_info(ctx: BattlefrontBotSlashContext, timeout: int = 600) -> None:
    embed = hikari.Embed(
        description=f"{ctx.author.display_name} has started matchmaking for Caps."
                    f"Register your interest below :point_down: ",
        colour=DEFAULT_EMBED_COLOUR
    )
    embed.set_footer(f"{LOADING_EMOJI} Waiting for players...")

    view = CapsRegisterView(timeout=timeout)

    message = await ctx.respond(embed=embed, components=view)

    ctx.app.miru_client.start_view(view, bind_to=message)
    await view.wait()

    registered_members = view.registered_members
    if len(registered_members) < 8:
        await message.edit(
            embed=hikari.Embed(
                description=f"{FAIL_EMOJI} Failed to get enough players",
                colour=FAIL_EMBED_COLOUR
            ),
            components=[]
        )
        return

    embed = hikari.Embed(description=f"{SUCCESS_EMOJI} Registration complete.", colour=DEFAULT_EMBED_COLOUR)
    embed.add_field(name="Participants:", value="\n".join([user.display_name for user in registered_members]))
    embed.set_footer(f"{LOADING_EMOJI} Starting session...")

    await message.edit(embed=embed, components=[])

    session = GameSession(ctx.get_guild(), registered_members)
    game_context = GameContext(ctx.app, ctx.get_channel(), ctx.member)

    await session.start(game_context)

    embed.set_footer(f"Session: {session.id}")
    await message.edit(embed=embed)


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
