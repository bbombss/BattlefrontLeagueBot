import asyncio
import bisect
import datetime
import os
from collections import Counter
from contextlib import suppress
from io import BytesIO
from random import randint

import hikari
import lightbulb
import miru

from src.models import (
    BattleFrontBot,
    BattlefrontBotPlugin,
    BattlefrontBotSlashContext,
    CapsRegisterView,
    DatabaseMember,
    GameSession,
    MapVotingView,
    SessionContext,
)
from src.models.database_match import DatabaseMatch
from src.static import *
from src.utils import bot_in_channel, generate_game_banner, is_admin

battlefront = BattlefrontBotPlugin("battlefront")
battlefront.add_checks(lightbulb.checks.guild_only)


@battlefront.command
@lightbulb.option("red", "The role for red (rank 3)", type=hikari.Role, required=True)
@lightbulb.option("yellow", "The role for yellow (rank 2)", type=hikari.Role, required=True)
@lightbulb.option("green", "The role for green (rank 1)", type=hikari.Role, required=True)
@lightbulb.option("white", "The role for white (rank 0)", type=hikari.Role, required=True)
@lightbulb.command("roles", description="Set the roles that determine player rank", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def set_roles(
    ctx: BattlefrontBotSlashContext, red: hikari.Role, yellow: hikari.Role, green: hikari.Role, white: hikari.Role
) -> None:
    if not is_admin(ctx.member):
        await ctx.respond_with_failure("**Only administrators can set roles**", ephemeral=True)
        return

    await ctx.app.db.execute(
        """
        UPDATE guilds
        SET rank1Role = $1, rank2Role = $2, rank3Role = $3, rank0Role = $4
        WHERE guildId = $5
        """,
        green.id,
        yellow.id,
        red.id,
        white.id,
        ctx.guild_id,
    )

    await ctx.respond_with_success("**Successfully updated rank roles**")


@battlefront.command
@lightbulb.option(
    "timeout", "How long the bot should wait for 8 players", default=30, type=int, required=False, max_value=999
)
@lightbulb.command("start", description="Starts a game session for this channel", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def start_caps(ctx: BattlefrontBotSlashContext, timeout: int) -> None:
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


@battlefront.command
@lightbulb.option("player", "The player to remove", type=hikari.Member, required=True)
@lightbulb.command("unregister", description="Force remove a player from registration", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def remove_player(ctx: BattlefrontBotSlashContext, player: hikari.Member) -> None:
    if not is_admin(ctx.member):
        await ctx.respond_with_failure("**Only a server administrator can do this**", ephemeral=True)
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


@battlefront.command
@lightbulb.option("team2score", "The score for team 2", type=int, required=True)
@lightbulb.option("team1score", "The score for team 1", type=int, required=True)
@lightbulb.command("score", description="Add a score to an ongoing session", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def caps_score(ctx: BattlefrontBotSlashContext, team1score: int, team2score: int) -> None:
    session = ctx.app.game_session_manager.fetch_session(ctx.channel_id)
    if not session or not session.session_task:
        await ctx.respond_with_failure("**Could not find a game session for this channel**", ephemeral=True)
        return
    if session.ctx.author.id != ctx.author.id:
        await ctx.respond_with_failure("**You cannot add a score to this session**", ephemeral=True)
        return

    ctx.app.game_session_manager.add_session_score(ctx.channel_id, team1score, team2score)
    await ctx.respond_with_success("**Added score to session successfully**", ephemeral=True)


@battlefront.command
@lightbulb.option("id", "The ID of the match", type=int, required=True)
@lightbulb.command("amend", description="Amend a match by swapping the winner and loser", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def amend_match(ctx: BattlefrontBotSlashContext, id: int) -> None:
    if not is_admin(ctx.member):
        await ctx.respond_with_failure("**Only administrators can amend matches**", ephemeral=True)
        return

    match = await DatabaseMatch.fetch(id)
    if not match.guild_id or match.guild_id != ctx.guild_id:
        await ctx.respond_with_failure("**No such match exists**", ephemeral=True)
        return

    if match.tied:
        await ctx.respond_with_failure("**Cannot amend a tied match**", ephemeral=True)
        return

    winner_score = int(match.winner_data["round1Score"]) + int(match.winner_data["round2Score"])
    loser_score = int(match.loser_data["round1Score"]) + int(match.loser_data["round2Score"])

    confirmation = await ctx.get_confirmation(
        f"**Are you sure you want to swap the winner and loser of this match:**\n"
        f"*Note: While wins and similar stats will be updated player ranking cannot and will not be altered*\n"
        f"Winner: **{match.winner_data['name']}** ({winner_score})\n"
        f"Loser: **{match.loser_data['name']}** ({loser_score})"
    )

    if confirmation:
        winner_data = match.winner_data
        match.winner_data = match.loser_data
        match.loser_data = winner_data
        await match.update()
        await match.amend_members()

        await ctx.respond_with_success("**Amended the match successfully**", edit=True)
        return

    await ctx.respond_with_failure("**Cancelled amending**", edit=True)


@battlefront.command
@lightbulb.option("player", "The player", type=hikari.Member, required=True)
@lightbulb.command("career", description="Shows a players stats", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def career(ctx: BattlefrontBotSlashContext, player: hikari.Member) -> None:
    db_member = await DatabaseMember.fetch(player.id, ctx.guild_id)
    if sum([db_member.wins, db_member.loses]) == 0:
        await ctx.respond_with_failure("**This player has no stats**")
        return

    ratings = {
        -5: "Well below average",
        -3: "Below average",
        -1: "Slightly below average",
        1: "Slightly above Average",
        3: "Above average",
        5: "Well above average",
    }
    thresholds = sorted(ratings)
    has_rating = True

    if db_member.mu is not None:
        ordinal = round(ctx.app.game_session_manager.openskill_model.rating(db_member.mu, db_member.sigma).ordinal(), 3)
        i = bisect.bisect_right(thresholds, round(ordinal)) - 1
        if i < 0:
            i = 0
        rating = ratings[thresholds[i]]
    else:
        has_rating = False

    embed = hikari.Embed(
        title=player.display_name,
        description=f"**Wins:** {db_member.wins}\n**Loses:** {db_member.loses}\n**Ties:** {db_member.ties}\n"
        f"**Win/loss:** {round((db_member.wins / (db_member.loses + db_member.wins + db_member.ties)), 3)}",
        colour=DEFAULT_EMBED_COLOUR,
    )
    if has_rating:
        embed.add_field(name="OpenSkill Rating:", value=f"**{ordinal}**\n{rating}")
    embed.set_thumbnail(player.avatar_url)
    await ctx.respond(embed=embed)


@battlefront.command
@lightbulb.add_cooldown(60, 3, lightbulb.buckets.GuildBucket)
@lightbulb.option("type", "Type of leaderboard to get", type=str, required=True, choices=["Wins", "Win/loss", "Ranks"])
@lightbulb.command("leaderboard", description="Shows the leaderboard for this server", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def leaderboard(ctx: BattlefrontBotSlashContext, type: str) -> None:
    records = await ctx.app.db.fetch(
        """
        WITH stats AS (
            SELECT
                userid,
                wins,
                loses,
                ties,
                mu,
                sigma,
                wins::float / NULLIF(wins + loses + ties, 0) AS win_loss,
                (mu - 3 * sigma) AS rating
            FROM members WHERE guildId = $1 AND mu IS NOT null
        )
        SELECT userid, wins, win_loss, rating FROM stats
        ORDER BY
            CASE WHEN $2 = 'Wins' THEN wins END DESC,
            CASE WHEN $2 = 'Win/loss' THEN win_loss END DESC,
            CASE WHEN $2 = 'Ranks' THEN rating END DESC
        LIMIT 10;
        """,
        ctx.guild_id,
        type,
    )

    if not records:
        await ctx.respond_with_failure("**This server has no stats**")
        return

    user_ids = [record["userid"] for record in records]
    members = [ctx.app.cache.get_member(ctx.guild_id, user_id) for user_id in user_ids]

    member_stats = {}
    for record, member in zip(records, members):
        if member is None:
            member = await ctx.app.rest.fetch_member(ctx.guild_id, record["userid"])

        if type == "Wins" and record["wins"] is not None:
            member_stats[member] = record["wins"]
        elif type == "Win/loss" and record["win_loss"] is not None:
            member_stats[member] = round(record["win_loss"], 3)
        elif type == "Ranks" and record["rating"] is not None:
            member_stats[member] = round(record["rating"], 3)

    if len(member_stats) == 0:
        await ctx.respond_with_failure("**This server has no stats**")
        return

    embed = hikari.Embed(
        title=f"{type} LeaderBoard",
        description="\n".join(f"**{member.display_name}:** {member_stats[member]}" for member in member_stats),
        colour=DEFAULT_EMBED_COLOUR,
    )
    await ctx.respond(embed=embed)


def map_image_path_for(map: str) -> str:
    """Get the path to the image for this map."""
    return os.path.join(battlefront.app.base_dir, "src", "static", "img", map.lower().replace(" ", "_") + ".jpg")


def get_map_choices() -> list[str]:
    """Get the list of maps excluding banned maps."""
    return [map for map in MAPS if MAPS[map] != 0]


def get_random_maps(index: int, amount: int, guild_id: hikari.Snowflake) -> list[str]:
    """Get a list of random maps.

    Parameters
    ----------
    index : int
        The minimum index that the maps can have.
    amount : int
        The amount of random maps to get.
    guild_id : hikari.Snowflake
        The ID of the guild these maps are being generated for.

    Returns
    -------
    list[str]
        A list of map names.

    """
    possible_maps = [map for map in MAPS if MAPS[map] >= index]
    maps = []

    for i in range(0, amount):
        rand_map = possible_maps[randint(0, len(possible_maps) - 1)]
        possible_maps.remove(rand_map)
        maps.append(rand_map)

    if len(maps) > 1 and battlefront.app.game_session_manager.last_map.get(guild_id):
        last_map = battlefront.app.game_session_manager.last_map[guild_id]
        maps.pop(-1)
        maps.append(last_map)
        battlefront.app.game_session_manager.last_map.pop(guild_id)

    return maps


@battlefront.command
@lightbulb.add_cooldown(60, 2, lightbulb.buckets.GuildBucket)
@lightbulb.option("index", "Map index, default is 1", type=int, required=False, min_value=1, max_value=3)
@lightbulb.option("amount", "Amount of random maps to generate", type=int, required=False, min_value=1, max_value=3)
@lightbulb.option("map3", "Custom map slot 3", type=str, required=False, choices=get_map_choices())
@lightbulb.option("map2", "Custom map slot 2", type=str, required=False, choices=get_map_choices())
@lightbulb.option("map1", "Custom map slot 1", type=str, required=False, choices=get_map_choices())
@lightbulb.command(
    "mapvote", description="Picks random maps or uses provided for players to vote on", pass_options=True
)
@lightbulb.implements(lightbulb.SlashCommand)
async def mapvote(
    ctx: BattlefrontBotSlashContext, index: int, amount: int, map1: str | None, map2: str | None, map3: str | None
) -> None:
    if not await bot_in_channel(ctx):
        await ctx.respond_with_failure("**The bot needs access to this channel for this command**", ephemeral=True)
        return

    if amount:
        maps = get_random_maps(index if index else 1, amount, ctx.guild_id)
    elif map1 and map2:
        maps = [map1, map2]
        if map3:
            maps.append(map3)
        if len(set(maps)) < len(maps):
            await ctx.respond_with_failure("**All custom maps must be unique**", ephemeral=True)
            return
    else:
        await ctx.respond_with_failure(
            "**You did not specify an amount of random maps or enough custom maps**", ephemeral=True
        )
        return

    await ctx.loading()

    urls = [map_image_path_for(map) for map in maps]

    if len(maps) == 1:
        embed = hikari.Embed(title=maps[0], colour=DEFAULT_EMBED_COLOUR).set_image(urls[0])
        await ctx.edit_last_response("", embed=embed)
        return

    players = None
    if session := ctx.app.game_session_manager.fetch_session(ctx.channel_id):
        players = [p.member for p in session.players]

    options = [miru.SelectOption(map, value=map) for map in maps]
    view = MapVotingView(players=players, timeout=60)
    view.get_item_by_id("mapvoteselect").options = options

    msg = await ctx.edit_last_response(
        f"Vote for a map: **{', '.join(map for map in maps)}**", attachments=[url for url in urls], components=view
    )

    ctx.app.miru_client.start_view(view, bind_to=msg)
    await view.wait()

    if len(view.votes) < 1:
        with suppress(hikari.NotFoundError):
            await ctx.respond_with_failure("**No one voted**", edit=True)
        return

    vote_counts = Counter(view.votes.values())
    winner_vote, winner_count = vote_counts.most_common(1)[0]

    try:
        await ctx.edit_last_response(
            "",
            embed=hikari.Embed(
                title=f"{winner_vote} won with {winner_count}/{len(view.votes)} votes", colour=DEFAULT_EMBED_COLOUR
            ).set_image(map_image_path_for(winner_vote)),
            components=[],
        )
    except hikari.NotFoundError:
        return

    if session := ctx.app.game_session_manager.fetch_session(ctx.channel_id):
        session.set_map(winner_vote)


@battlefront.command
@lightbulb.add_cooldown(60, 3, lightbulb.buckets.GuildBucket)
@lightbulb.option("name", "Name of the map", type=str, required=True, choices=[map for map in MAPS if MAPS[map] != 0])
@lightbulb.command("map", description="Get a map", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def get_map(ctx: BattlefrontBotSlashContext, name: str) -> None:
    with suppress(hikari.ForbiddenError):
        await ctx.app.rest.trigger_typing(ctx.channel_id)

    img_path = os.path.join(ctx.app.base_dir, "src", "static", "img", name.lower().replace(" ", "_") + ".jpg")

    await ctx.respond(embed=hikari.Embed(title=name, colour=DEFAULT_EMBED_COLOUR).set_image(img_path))

    ctx.app.game_session_manager.last_map[ctx.channel_id] = name
    if session := ctx.app.game_session_manager.fetch_session(ctx.channel_id):
        session.set_map(name)


@battlefront.command
@lightbulb.option("id", "The id for the match", type=int, required=True)
@lightbulb.command("match", description="Shows a summary for the given match", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def matchsummary(ctx: BattlefrontBotSlashContext, id: int) -> None:
    match = await DatabaseMatch.fetch(id)
    if not match.guild_id or match.guild_id != ctx.guild_id:
        await ctx.respond_with_failure("**No such match exists**", ephemeral=True)
        return

    with suppress(hikari.ForbiddenError):
        await ctx.app.rest.trigger_typing(ctx.channel_id)

    winner_score = int(match.winner_data["round1Score"]) + int(match.winner_data["round2Score"])
    loser_score = int(match.loser_data["round1Score"]) + int(match.loser_data["round2Score"])
    winner_names = []
    loser_names = []

    guild_members = await ctx.app.rest.fetch_members(ctx.guild_id)
    for member in guild_members:
        if member.id in match.winner_data["playerIds"]:
            winner_names.append(member.display_name)
        if member.id in match.loser_data["playerIds"]:
            loser_names.append(member.display_name)

    b: BytesIO = await asyncio.get_running_loop().run_in_executor(
        None,
        generate_game_banner,
        [match.winner_data["name"], match.loser_data["name"]],
        (winner_score, loser_score),
        winner_names,
    )

    description = f"{match.winner_data['name']} won" if not match.tied else "Teams tied"

    embed = hikari.Embed(
        title=f"{match.winner_data['name']} vs {match.loser_data['name']}",
        description=f"**{description} {winner_score} - {loser_score}**",
        colour=DEFAULT_EMBED_COLOUR,
        timestamp=match.date.astimezone(datetime.timezone.utc),
    )
    embed.add_field(name=match.winner_data["name"], value=", ".join(winner_names))
    embed.add_field(name=match.loser_data["name"], value=", ".join(loser_names))
    embed.set_footer(str(match.id))
    embed.set_image(hikari.Bytes(b.getvalue(), "banner.jpg"))

    await ctx.respond(embed=embed)


@battlefront.command
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
async def forcestart(
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


@battlefront.command
@lightbulb.command("flushcache", description="Clear the player cache for this server")
@lightbulb.implements(lightbulb.SlashCommand)
async def flushcache(ctx: BattlefrontBotSlashContext) -> None:
    if not is_admin(ctx.member):
        await ctx.respond_with_failure("**You cannot do this**", ephemeral=True)
        return

    ctx.app.game_session_manager.player_cache.clear_guild(ctx.guild_id)
    await ctx.respond_with_success("**Flushed guild player cache**", ephemeral=True)


@battlefront.command
@lightbulb.command("end", description="Stops an ongoing session")
@lightbulb.implements(lightbulb.SlashCommand)
async def end_session(ctx: BattlefrontBotSlashContext) -> None:
    session = ctx.app.game_session_manager.fetch_session(ctx.channel_id)
    if not session:
        await ctx.respond_with_failure("**Could not find a game session for this channel**", ephemeral=True)
        return

    if session.ctx.author.id != ctx.author.id and not is_admin(ctx.member):
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
