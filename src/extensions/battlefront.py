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
    DatabaseMember,
    MapVotingView,
    SettingsView,
)
from src.models.database_match import DatabaseMatch
from src.static import *
from src.utils import bot_in_channel, generate_game_banner, is_admin, is_bot_admin

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
    if not await is_bot_admin(ctx):
        await ctx.respond_with_failure("**Only bot admins for this server can set roles**", ephemeral=True)
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
@lightbulb.option("id", "The ID of the match", type=int, required=True)
@lightbulb.command("amend", description="Amend a match by swapping the winner and loser", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def amend_match(ctx: BattlefrontBotSlashContext, id: int) -> None:
    if not await is_bot_admin(ctx):
        await ctx.respond_with_failure("**Only bot admins for this server can amend matches**", ephemeral=True)
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
@lightbulb.add_cooldown(60, 4, lightbulb.buckets.GuildBucket)
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


async def index_banned_maps(ctx: BattlefrontBotSlashContext) -> dict[str, int]:
    """Index maps by distance from banned map.

    Parameters
    ----------
    ctx : BattlefrontBotSlashContext
        The context to fetch banned maps for.

    Returns
    -------
    dict[str, int]
        A dictionary of map names and their respective index.

    """
    map_records = await ctx.app.db.fetch("""SELECT * FROM mapBans WHERE guildId = $1""", ctx.guild_id)
    banned_maps = set([record["mapname"] for record in map_records])
    distances: dict[str, int] = {}
    counter: int = 0

    for map in reversed(MAPS):
        if map in banned_maps:
            counter = 0
        else:
            counter += 1

        distances[map] = counter

    return {map: distances[map] for map in MAPS}


def get_random_maps(maps_table: dict[str, int], index: int, amount: int, guild_id: hikari.Snowflake) -> list[str]:
    """Get a list of random maps.

    Parameters
    ----------
    maps_table : dict[str, int]
        A list of indexed maps with bans.
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
    possible_maps = [map for map in maps_table if maps_table[map] >= index]
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
@lightbulb.add_cooldown(60, 4, lightbulb.buckets.GuildBucket)
@lightbulb.option("index", "Map index, default is 1", type=int, required=False, min_value=1, max_value=3)
@lightbulb.option("amount", "Amount of random maps to generate", type=int, required=False, min_value=1, max_value=3)
@lightbulb.option("map3", "Custom map slot 3", type=str, required=False, choices=MAPS)
@lightbulb.option("map2", "Custom map slot 2", type=str, required=False, choices=MAPS)
@lightbulb.option("map1", "Custom map slot 1", type=str, required=False, choices=MAPS)
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

    indexed_maps = await index_banned_maps(ctx)

    if amount:
        maps = get_random_maps(indexed_maps, index if index else 1, amount, ctx.guild_id)
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
@lightbulb.add_cooldown(60, 5, lightbulb.buckets.GuildBucket)
@lightbulb.option("name", "Name of the map", type=str, required=True, choices=MAPS)
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
async def match_summary(ctx: BattlefrontBotSlashContext, id: int) -> None:
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

    winners = [ctx.app.cache.get_member(ctx.guild_id, user_id) for user_id in match.winner_data["playerIds"]]
    losers = [ctx.app.cache.get_member(ctx.guild_id, user_id) for user_id in match.loser_data["playerIds"]]

    for record, member in zip(match.winner_data["playerIds"], winners):
        if member is None:
            try:
                member = await ctx.app.rest.fetch_member(ctx.guild_id, record)
            except hikari.NotFoundError:
                winner_names.append("Unknown Member")
                continue
        winner_names.append(member.display_name)

    for record, member in zip(match.loser_data["playerIds"], losers):
        if member is None:
            try:
                member = await ctx.app.rest.fetch_member(ctx.guild_id, record)
            except hikari.NotFoundError:
                winner_names.append("Unknown Member")
                continue
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
@lightbulb.command("history", description="Shows the 3 most recent matches", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def match_history(ctx: BattlefrontBotSlashContext) -> None:
    record = await ctx.app.db.fetch("SELECT matchId FROM matches ORDER BY matchId DESC LIMIT 3")

    if record[0]["matchid"] < 3:
        await ctx.respond_with_failure("Not enough matches exist", ephemeral=True)
        return

    match1 = await DatabaseMatch.fetch(record[0]["matchid"])
    match2 = await DatabaseMatch.fetch(record[1]["matchid"])
    match3 = await DatabaseMatch.fetch(record[2]["matchid"])

    embed = hikari.Embed(
        title="Match History", description="Last 3 matches for this server", colour=DEFAULT_EMBED_COLOUR
    )

    embed.add_field(
        name=f"{match1.winner_data['name']} vs {match1.loser_data['name']} ({match1.id})",
        value=f"{match1.winner_data['name']} wins\n{match1.date.astimezone(TIMEZONE).strftime('%H:%M %d/%m/%Y')}",
    )
    embed.add_field(
        name=f"{match2.winner_data['name']} vs {match2.loser_data['name']} ({match2.id})",
        value=f"{match2.winner_data['name']} wins\n{match2.date.astimezone(TIMEZONE).strftime('%H:%M %d/%m/%Y')}",
    )
    embed.add_field(
        name=f"{match3.winner_data['name']} vs {match3.loser_data['name']} ({match3.id})",
        value=f"{match3.winner_data['name']} wins\n{match3.date.astimezone(TIMEZONE).strftime('%H:%M %d/%m/%Y')}",
    )

    await ctx.respond(embed=embed)


@battlefront.command
@lightbulb.command("flushcache", description="Clear the player cache for this server")
@lightbulb.implements(lightbulb.SlashCommand)
async def flushcache(ctx: BattlefrontBotSlashContext) -> None:
    if not await is_bot_admin(ctx):
        await ctx.respond_with_failure("**You cannot do this**", ephemeral=True)
        return

    ctx.app.game_session_manager.player_cache.clear_guild(ctx.guild_id)
    await ctx.respond_with_success("**Flushed guild player cache**", ephemeral=True)


@battlefront.command
@lightbulb.command("settings", description="Configure the bot")
@lightbulb.implements(lightbulb.SlashCommand)
async def bot_settings(ctx: BattlefrontBotSlashContext) -> None:
    if not is_admin(ctx.member):
        await ctx.respond_with_failure("**Only server administrators can alter these settings**", ephemeral=True)
        return

    view = SettingsView(ctx)
    msg = await ctx.respond(embed=await view.build_embed(), components=view)

    ctx.app.miru_client.start_view(view, bind_to=msg)
    await view.wait()


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
