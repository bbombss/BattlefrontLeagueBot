import hikari
import lightbulb

from src.models import (
    BattleFrontBot,
    BattlefrontBotPlugin,
    BattlefrontBotSlashContext,
    CapsRegisterView,
    GameSession,
    SessionContext,
    DatabaseMember
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
                1384108414937993338,
            ],
        ),
        Fakemember(
            2,
            "fake2",
            [
                1384108414937993338,
            ],
        ),
        Fakemember(
            3,
            "fake3",
            [
                1384108414937993338,
            ],
        ),
        Fakemember(
            4,
            "fake4",
            [
                1384108482516488343,
            ],
        ),
        Fakemember(
            5,
            "fake5",
            [
                1384108482516488343,
            ],
        ),
        Fakemember(
            6,
            "fake6",
            [
                1384108535478095883,
            ],
        ),
        Fakemember(
            7,
            "fake7",
            [
                1384108535478095883,
            ],
        ),
        Fakemember(
            8,
            "fake8",
            [
                1384108535478095883,
            ],
        ),
    ]


@battlefront.command
@lightbulb.option("greencaps", "The role for green caps", type=hikari.Role, required=True)
@lightbulb.option("yellowcaps", "The role for yellow caps", type=hikari.Role, required=True)
@lightbulb.option("redcaps", "The role for red caps", type=hikari.Role, required=True)
@lightbulb.command("roles", description="Set the roles that determine player rank", pass_options=True)
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
@lightbulb.command("start", description="Starts a game session", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def startcaps(ctx: BattlefrontBotSlashContext, timeout: int) -> None:
    if not timeout:
        timeout = 30

    if ctx.app.game_session_manager.fetch_session(ctx.guild_id):
        await ctx.respond_with_failure("**There is already a game session running in this server**", ephemeral=True)
        return

    record = await ctx.app.db.fetchrow("SELECT * FROM guilds WHERE guildId = $1", ctx.guild_id)
    assert record is not None
    if record["rank1role"] is None or record["rank2role"] is None or record["rank3role"] is None:
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

    view = CapsRegisterView(embed, author=ctx.member.id, timeout=timeout*60)

    message = await ctx.respond(embed=embed, components=view)

    ctx.app.miru_client.start_view(view, bind_to=message)
    await view.wait()
    view.registered_members = get_fake_members()  # del

    if len(view.registered_members) < 8:
        await message.edit(
            embed=hikari.Embed(description=f"{FAIL_EMOJI} **Not enough players registered**", colour=FAIL_EMBED_COLOUR),
            components=[],
        )
        return
    elif len(view.registered_members) > 8:
        await message.edit(
            embed=hikari.Embed(description=f"{FAIL_EMOJI} **Too many players registered**", colour=FAIL_EMBED_COLOUR),
            components=[],
        )
        return

    embed = hikari.Embed(description=f"{SUCCESS_EMOJI} **Registration Complete**", colour=DEFAULT_EMBED_COLOUR)
    embed.add_field(name="Participants:", value="\n".join([user.display_name for user in view.registered_members]))
    embed.set_footer("Starting session...")

    await message.edit(embed=embed, components=[])

    game_context = SessionContext(ctx.app, ctx.get_guild(), ctx.get_channel(), ctx.member)
    session = GameSession(game_context)

    embed.set_footer(f"Session: {ctx.app.game_session_manager.session_count + 1}")
    await message.edit(embed=embed)

    await ctx.app.game_session_manager.start_session(ctx.guild_id, session, view.registered_members)


@battlefront.command
@lightbulb.option("team2score", "The score for team 2", type=int, required=True)
@lightbulb.option("team1score", "The score for team 1", type=int, required=True)
@lightbulb.command("score", description="Add a score to an ongoing session", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def capsresult(ctx: BattlefrontBotSlashContext, team1score: int, team2score: int) -> None:
    session = ctx.app.game_session_manager.fetch_session(ctx.guild_id)
    if not session or not session.session_task:
        await ctx.respond_with_failure("**Could not find a game session for this server**", ephemeral=True)
        return
    if session.ctx.author.id != ctx.author.id:
        await ctx.respond_with_failure("**You cannot add a score to this session**", ephemeral=True)
        return

    ctx.app.game_session_manager.add_session_score(ctx.guild_id, team1score, team2score)
    await ctx.respond_with_success("**Added score to session successfully**", ephemeral=True)


@battlefront.command
@lightbulb.option("player", "The player", type=hikari.Member, required=True)
@lightbulb.command("career", description="Shows a players stats", pass_options=True)
@lightbulb.implements(lightbulb.SlashCommand)
async def career(ctx: BattlefrontBotSlashContext, player: hikari.Member) -> None:
    db_member = await DatabaseMember.fetch(player.id, ctx.guild_id)
    if sum([db_member.wins, db_member.loses]) == 0:
        await ctx.respond_with_failure("**This player has no stats**", ephemeral=True)
        return

    embed = hikari.Embed(
        title=player.display_name,
        description=f"**Wins:** {db_member.wins}\n**Loses:** {db_member.loses}\n"
                    f"**Win/loss:** {round((db_member.wins / (db_member.loses + db_member.wins)), 3)}",
        colour=DEFAULT_EMBED_COLOUR
    )
    embed.set_thumbnail(player.avatar_url)
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
        ctx: BattlefrontBotSlashContext, player1: hikari.Member, player2: hikari.Member,
        player3: hikari.Member, player4: hikari.Member, player5: hikari.Member, player6: hikari.Member,
        player7: hikari.Member, player8: hikari.Member
) -> None:
    if ctx.app.game_session_manager.fetch_session(ctx.guild_id):
        await ctx.respond_with_failure("**There is already a game session running in this server**", ephemeral=True)
        return

    game_context = SessionContext(ctx.app, ctx.get_guild(), ctx.get_channel(), ctx.member)
    session = GameSession(game_context)

    players = [player1, player2, player3, player4, player5, player6, player7, player8]

    await ctx.respond_with_success("**Started a match with forced teams**", ephemeral=True)
    await ctx.app.game_session_manager.start_session(ctx.guild_id, session, players, force=True)


@battlefront.command
@lightbulb.command("end", description="Stops an ongoing session")
@lightbulb.implements(lightbulb.SlashCommand)
async def endsession(ctx: BattlefrontBotSlashContext) -> None:
    session = ctx.app.game_session_manager.fetch_session(ctx.guild_id)
    if not session or not session.session_task:
        await ctx.respond_with_failure("**Could not find a game session for this server**", ephemeral=True)
        return
    if session.ctx.author.id != ctx.author.id and not is_admin(ctx.member):
        await ctx.respond_with_failure("**You cannot end this session**", ephemeral=True)
        return

    ctx.app.game_session_manager.end_session(ctx.guild_id)
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
