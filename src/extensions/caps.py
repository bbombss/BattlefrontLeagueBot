from contextlib import suppress

import hikari
import lightbulb
import miru

from src.models import (
    BattleFrontBot,
    BattlefrontBotPlugin,
    BattlefrontBotSlashContext,
    CapsRegisterView,
    GameSession,
    SessionContext,
)
from src.static import *
from src.utils import bot_in_channel, is_bot_admin

caps = BattlefrontBotPlugin("caps")
caps.add_checks(lightbulb.checks.guild_only)


@caps.command
@lightbulb.option(
    "timeout", "How long the bot should wait for 8 players", default=30, type=int, required=False, max_value=999
)
@lightbulb.command("start", description="Starts a game session for this channel", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def caps_start(ctx: BattlefrontBotSlashContext, timeout: int) -> None:
    channel = ctx.get_channel()

    if not await bot_in_channel(ctx) or not isinstance(channel, hikari.TextableGuildChannel):
        await ctx.respond_with_failure("**The bot needs access to this channel for this command**", ephemeral=True)
        return

    if ctx.app.game_session_manager.fetch_session(ctx.channel_id):
        await ctx.respond_with_failure("**There is already a game session running in this channel**", ephemeral=True)
        return

    record = await ctx.app.db.fetchrow("SELECT * FROM guilds WHERE guildId = $1", ctx.guild_id)
    if not record or None in [record[f"rank{i}role"] for i in range(0, 4)]:
        await ctx.respond_with_failure(
            "Could not find rank roles for server, use `/roles` to configure rank roles", ephemeral=True
        )
        return

    embed = hikari.Embed(
        description=f"**{ctx.author.display_name} has started matchmaking for Caps.\n"
        f"Register your interest below** :point_down:",
        colour=DEFAULT_EMBED_COLOUR,
    )
    embed.set_footer("Waiting for players...")

    view = CapsRegisterView(embed, author=ctx.member.id, timeout=timeout * 60)

    resp = await ctx.respond(embed=embed, components=view)

    message = await resp.message()
    ctx.app.game_session_manager.last_registration_message[ctx.channel_id] = message.id
    ctx.app.miru_client.start_view(view, bind_to=message)
    await view.wait()

    if len(view.registered_members) < 8:
        with suppress(hikari.NotFoundError):
            await message.edit(
                embed=hikari.Embed(
                    description=f"{FAIL_EMOJI} **Not enough players registered**", colour=FAIL_EMBED_COLOUR
                ),
                components=[],
            )
        return

    embed = hikari.Embed(description=f"{SUCCESS_EMOJI} **Registration Complete**", colour=DEFAULT_EMBED_COLOUR)
    embed.add_field(name="Participants:", value="\n".join([user.display_name for user in view.registered_members]))
    embed.set_footer(f"Session: {ctx.app.game_session_manager.session_count + 1}")

    if ctx.app.game_session_manager.fetch_session(ctx.channel_id):
        embed = hikari.Embed(
            description=f"{FAIL_EMOJI} **Registration cancelled because there is another session in this channel**",
            colour=FAIL_EMBED_COLOUR,
        )

    await message.edit(embed=embed, components=[])
    await ctx.app.rest.create_message(ctx.channel_id, f"{ctx.user.mention}", user_mentions=True)

    session = GameSession(SessionContext(ctx.app, ctx.get_guild(), channel, ctx.member))

    await ctx.app.game_session_manager.start_session(ctx.channel_id, session, view.registered_members)


@caps.command
@lightbulb.option("player", "The player to remove", type=hikari.Member, required=True)
@lightbulb.command("unregister", description="Force remove a player from registration", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def caps_remove_player(ctx: BattlefrontBotSlashContext, player: hikari.Member) -> None:
    if not await is_bot_admin(ctx):
        await ctx.respond_with_failure("**Only a bot admin for this server can do this**", ephemeral=True)
        return

    view: miru.View | None = None
    if message_id := ctx.app.game_session_manager.last_registration_message[ctx.channel_id]:
        view = ctx.app.miru_client.get_bound_view(message_id)

    if view is None or not isinstance(view, CapsRegisterView):
        await ctx.respond_with_failure("**No registration component found for this channel**", ephemeral=True)
        return

    if not any(player.id == m.id for m in view.registered_members):
        await ctx.respond_with_failure("**This player is not already in the queue**", ephemeral=True)
        return

    for m in view.registered_members:
        if player.id == m.id:
            view.registered_members.pop(view.registered_members.index(m))

    view.embed.remove_field(0)
    if len(view.registered_members) > 1:
        await view.update_embed()
    else:
        await view.message.edit(embed=view.embed)

    await ctx.respond_with_success("**Removed player from queue**", ephemeral=True)


@caps.command
@lightbulb.option("player", "The player to add", type=hikari.Member, required=True)
@lightbulb.command("register", description="Force add a player to registration", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def caps_add_player(ctx: BattlefrontBotSlashContext, player: hikari.Member) -> None:
    if not await is_bot_admin(ctx):
        await ctx.respond_with_failure("**Only a bot admin for this server can do this**", ephemeral=True)
        return

    view: miru.View | None = None
    if message_id := ctx.app.game_session_manager.last_registration_message[ctx.channel_id]:
        view = ctx.app.miru_client.get_bound_view(message_id)

    if view is None or not isinstance(view, CapsRegisterView):
        await ctx.respond_with_failure(
            "**No registration component found for this channel**\nor the component has no previous interactions",
            ephemeral=True,
        )
        return

    if any(player.id == m.id for m in view.registered_members):
        await ctx.respond_with_failure("**This player is already in the queue**", ephemeral=True)
        return

    view.registered_members.append(player)

    view.embed.remove_field(0)
    await view.update_embed()

    await ctx.respond_with_success("**Added player to the queue**", ephemeral=True)


@caps.command
@lightbulb.command("sub", description="Sub in to an ongoing session", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def caps_sub(ctx: BattlefrontBotSlashContext) -> None:
    session = ctx.app.game_session_manager.fetch_session(ctx.channel_id)
    if not session or not session.session_task:
        await ctx.respond_with_failure("**Could not find a game session for this channel**", ephemeral=True)
        return

    success = await ctx.app.game_session_manager.add_sub(ctx.channel_id, ctx.member)
    if success:
        await ctx.respond_with_success("**You are in the subs queue**", ephemeral=True)
    else:
        await ctx.respond_with_failure("**This player cannot be subbed in**", ephemeral=True)


@caps.command
@lightbulb.option("player", "The player to remove if provided", type=hikari.Member, required=False)
@lightbulb.command("leave", description="Leave an ongoing session or remove a player", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def caps_leave(ctx: BattlefrontBotSlashContext, player: hikari.Member) -> None:
    session = ctx.app.game_session_manager.fetch_session(ctx.channel_id)
    if not session or not session.session_task:
        await ctx.respond_with_failure("**Could not find a game session for this channel**", ephemeral=True)
        return

    if player is not None and not await is_bot_admin(ctx):
        await ctx.respond_with_failure("**You are not allowed to remove another player**", ephemeral=True)
        return

    if player is None:
        player = ctx.member

    success = await ctx.app.game_session_manager.remove_player(ctx.channel_id, player)
    if success:
        await ctx.respond_with_success("**Removed from match successfully**", ephemeral=True)
    else:
        await ctx.respond_with_failure(
            "**This player cannot be removed because they are either not in the session or "
            "their are no subs to replace them**",
            ephemeral=True,
        )


@caps.command
@lightbulb.option("team2score", "The score for team 2", type=int, required=True)
@lightbulb.option("team1score", "The score for team 1", type=int, required=True)
@lightbulb.command("score", description="Add a score to an ongoing session", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def caps_score(ctx: BattlefrontBotSlashContext, team1score: int, team2score: int) -> None:
    session = ctx.app.game_session_manager.fetch_session(ctx.channel_id)
    if not session or not session.session_task:
        await ctx.respond_with_failure("**Could not find a game session for this channel**", ephemeral=True)
        return
    if session.ctx.author.id != ctx.author.id and not await is_bot_admin(ctx):
        await ctx.respond_with_failure("**You cannot add a score to this session**", ephemeral=True)
        return

    ctx.app.game_session_manager.add_session_score(ctx.channel_id, team1score, team2score)
    await ctx.respond_with_success("**Added score to session successfully**", ephemeral=True)


@caps.command
@lightbulb.option("player8", "Team 2", type=hikari.Member, required=True)
@lightbulb.option("player7", "Team 2", type=hikari.Member, required=True)
@lightbulb.option("player6", "Team 2", type=hikari.Member, required=True)
@lightbulb.option("player5", "Team 2", type=hikari.Member, required=True)
@lightbulb.option("player4", "Team 1", type=hikari.Member, required=True)
@lightbulb.option("player3", "Team 1", type=hikari.Member, required=True)
@lightbulb.option("player2", "Team 1", type=hikari.Member, required=True)
@lightbulb.option("player1", "Team 1", type=hikari.Member, required=True)
@lightbulb.command("forcestart", description="Starts Caps with a forced set of teams", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def caps_forcestart(
    ctx: BattlefrontBotSlashContext,
    player1: hikari.Member,
    player2: hikari.Member,
    player3: hikari.Member,
    player4: hikari.Member,
    player5: hikari.Member,
    player6: hikari.Member,
    player7: hikari.Member,
    player8: hikari.Member,
) -> None:
    channel = ctx.get_channel()

    if not await bot_in_channel(ctx) or not isinstance(channel, hikari.TextableGuildChannel):
        await ctx.respond_with_failure("**The bot needs access to this channel for this command**", ephemeral=True)
        return

    if ctx.app.game_session_manager.fetch_session(ctx.channel_id):
        await ctx.respond_with_failure("**There is already a game session running in this channel**", ephemeral=True)
        return

    record = await ctx.app.db.fetchrow("SELECT * FROM guilds WHERE guildId = $1", ctx.guild_id)
    if not record or None in [record[f"rank{i}role"] for i in range(0, 4)]:
        await ctx.respond_with_failure(
            "Could not find rank roles for server, use `/roles` to configure rank roles", ephemeral=True
        )
        return

    players = [player1, player2, player3, player4, player5, player6, player7, player8]

    if len({m.id for m in players}) != len(players):
        await ctx.respond_with_failure("**Duplicate users were given** each player must be unique", ephemeral=True)
        return

    session = GameSession(SessionContext(ctx.app, ctx.get_guild(), channel, ctx.member))

    await ctx.respond_with_success(
        f"**Started a match with forced teams: {ctx.app.game_session_manager.session_count + 1}**", ephemeral=True
    )
    await ctx.app.game_session_manager.start_session(ctx.channel_id, session, players, force=True)


@caps.command
@lightbulb.command("end", description="Stops an ongoing session")
@lightbulb.implements(lightbulb.SlashCommand)
async def caps_end(ctx: BattlefrontBotSlashContext) -> None:
    session = ctx.app.game_session_manager.fetch_session(ctx.channel_id)
    if not session:
        await ctx.respond_with_failure("**Could not find a game session for this channel**", ephemeral=True)
        return

    if session.ctx.author.id != ctx.author.id and not await is_bot_admin(ctx):
        await ctx.respond_with_failure("**You cannot end this session**", ephemeral=True)
        return

    if not session.session_task:
        ctx.app.game_session_manager.remove_session(ctx.channel_id)
        await ctx.respond_with_failure("**Could not connect to session but ended it anyway**", ephemeral=True)
        return

    ctx.app.game_session_manager.end_session(ctx.channel_id)
    ctx.app.game_session_manager.remove_session(ctx.channel_id)  # Just in case

    await ctx.respond_with_success("**Ended session successfully**", ephemeral=True)


def load(bot: BattleFrontBot) -> None:
    bot.add_plugin(caps)


def unload(bot: BattleFrontBot) -> None:
    bot.remove_plugin(caps)


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
