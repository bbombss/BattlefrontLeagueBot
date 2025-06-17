from __future__ import annotations

__all__ = ["GameSession", "SessionContext"]

import asyncio
import itertools
import typing as t
from collections import Counter
from random import randint

import hikari

if t.TYPE_CHECKING:
    from src.models.bot import BattleFrontBot

from src.models.errors import *
from src.models.views import CapsVotingView, RetryView
from src.static import *


def create_team_name() -> str:
    """Create a team name from the 2 team seed wordlists."""
    name = (
        TEAM_NAME_KEY_1[randint(0, len(TEAM_NAME_KEY_1) - 1)]
        + " "
        + TEAM_NAME_KEY_2[randint(0, len(TEAM_NAME_KEY_2) - 1)]
    )
    return name


class GamePlayer:
    """Player object for GameSessions."""

    def __init__(self, member: hikari.Member, name: str, role: int) -> None:
        """Player object for GameSessions.

        Parameters
        ----------
        member : hikari.Member
            The member that corresponds to this player.
        name : str
            The name of this player.
        role : int
            The role rank this player has.

        """
        self.member = member
        self.name = name
        self.role = role


class GameTeam:
    """Team object for GameSessions."""

    def __init__(self, players: list[GamePlayer], name: str, skill: int) -> None:
        """Team object for GameSessions.

        Parameters
        ----------
        players : list[GamePlayer]
            A list of GamePlayers that are in this team.
        name : str
            The name of this team.
        skill : int
            The total skill score from all players in this team.

        """
        self.players = players
        self.name = name
        self.skill = skill


class SessionContext:
    """Context object for GameSessions."""

    def __init__(self, app: BattleFrontBot, guild: hikari.Guild, channel: hikari.GuildChannel, author: hikari.Member):
        """Context object for GameSessions.

        Parameters
        ----------
        app : BattleFrontBot
            The app this context is tied to.
        guild : hikari.Guild
            The guild this context was created for.
        channel : hikari.GuildChannel
            The channel this context was created for.
        author : hikari.Member
            The memeber this context was created for (i.e. the session initiator).

        """
        self._app = app
        self._guild = guild
        self._channel = channel
        self._author = author
        self._last_response: hikari.Message

    @property
    def app(self) -> BattleFrontBot:
        """The app this context is tied to."""
        return self._app

    @property
    def guild(self) -> hikari.Guild:
        """The guild this context was created for."""
        return self._guild

    @property
    def channel(self) -> hikari.GuildChannel:
        """The channel this context was created for."""
        return self._channel

    @property
    def author(self) -> hikari.Member:
        """The member this context was created for (i.e. the session initiator)."""
        return self._author

    @property
    def last_response(self) -> hikari.Message | None:
        """The last response made for this context or None if there are no responses."""
        return self._last_response

    async def respond(self, *args, **kwargs) -> hikari.Message:
        """Create a response for this context.

        Parameters
        ----------
        args : Any
            Arguments passed to the message builder.
        kwargs : Any
            Keyword arguments passed to the message builder.

        Returns
        -------
        hikari.Message
            The resulting created message.

        """
        msg = await self.app.rest.create_message(self.channel, *args, **kwargs)
        self._last_response = msg

        return msg

    async def edit_last_response(self, *args, **kwargs) -> hikari.Message | None:
        """Edit the last response created for this context.

        Parameters
        ----------
        args : Any
            Arguments passed to the message builder.
        kwargs : Any
            Keyword arguments passed to the message builder.

        Returns
        -------
        hikari.Message | None
            The resulting created message or None if there is no previous response.

        """
        if not self.last_response:
            return

        msg = await self.last_response.edit(*args, **kwargs)
        self._last_response = msg

        return msg

    async def wait(self) -> hikari.Message:
        """Create a response with loading a message."""
        return await self.respond(f"{LOADING_EMOJI} Waiting for server...")

    async def retry(
        self, *args, author: hikari.Snowflake | None = None, timeout: float = 60, edit: bool = False, **kwargs
    ) -> bool:
        """Create a response for this context.

        Parameters
        ----------
        args : Any
            Arguments passed to the message builder.
        author : Any
            An author id, if given only the author can retry, defaults to None.
        timeout : float
            Timeout for view, defaults to 60.
        edit : bool
            Whether the original response should be edited, defaults to False.
        kwargs : Any
            Keyword arguments passed to the message builder.

        Returns
        -------
        bool
            True if the user prompted for retry.

        """
        view = RetryView(author=author, timeout=timeout)

        if edit:
            msg = await self.edit_last_response(*args, components=view, **kwargs)
        else:
            msg = await self.respond(*args, components=view, **kwargs)

        self._last_response = msg
        self.app.miru_client.start_view(view, bind_to=msg)
        await view.wait()
        return view.value

    async def team_vote(self, timeout: float = 30, edit: bool = False, **kwargs) -> int | None:
        """Poll players for their team preference and returns the winning vote.

        Parameters
        ----------
        timeout : float
            Timeout for view, defaults to 30.
        edit : bool
            Whether the original response should be edited, defaults to False.
        kwargs : Any
            Keyword arguments passed to the message builder.

        Returns
        -------
        int | None
            Returns the winning vote or None if there were no votes.

        """
        view = CapsVotingView(timeout=timeout)

        if edit:
            msg = await self.edit_last_response("", components=view, **kwargs)
        else:
            msg = await self.respond(components=view, **kwargs)

        self._last_response = msg
        self.app.miru_client.start_view(view, bind_to=msg)
        await view.wait()

        if len(view.votes) < 1:
            return

        vote_counts = Counter(view.votes.values())
        winner_vote, winner_count = vote_counts.most_common(1)[0]
        return winner_vote


class GameSession:
    """Session object that is used to track game progress and stats."""

    def __init__(self, ctx: SessionContext) -> None:
        """Session object that is used to track game progress and stats.

        Parameters
        ----------
        ctx : SessionContext
            The context object for this session.

        """
        self._ctx = ctx
        self._players: list[GamePlayer]
        self._rank_roles: dict[str, hikari.Snowflake]
        self._id: int
        self._session_task: asyncio.Task
        self._session_manager = ctx.app.game_session_manager

    @property
    def ctx(self) -> SessionContext:
        """The game context object for this session."""
        return self._ctx

    @property
    def players(self) -> list[GamePlayer]:
        """List of GamePlayers participating in this session."""
        if self._players is None:
            raise GameSessionError("Session must be started to access property players")
        return self._players

    @property
    def id(self) -> int:
        """The id of this session."""
        if self._id is None:
            raise GameSessionError("Session must be started to access property id")
        return self._id

    @property
    def rank_roles(self) -> dict[str, hikari.Snowflake]:
        """The rank roles to identify player ranks for this session."""
        if self._rank_roles is None:
            raise GameSessionError("Session must be started to access property rank_roles")
        return self._rank_roles

    async def _fetch_rank_roles(self) -> None:
        """Fetch the rank role ids for this session from the database."""
        record = await self.ctx.app.db.fetchrow("SELECT * FROM guilds WHERE guildId = $1", self.ctx.guild.id)
        self._rank_roles = {
            "1": hikari.Snowflake(record["rank1role"]),
            "2": hikari.Snowflake(record["rank2role"]),
            "3": hikari.Snowflake(record["rank3role"]),
        }

    async def _get_player_object(self, member: hikari.Member) -> GamePlayer:
        """Get a GamePlayer object for this member.

        Parameters
        ----------
        member : hikari.Member
            The member to get a GamePlayer object for.

        Returns
        -------
        GamePlayer
            A GamePlayer object that corresponds the member.

        """
        rank_role: int | None = None

        for role in member.role_ids:
            if role == self.rank_roles["1"]:
                rank_role = 1
                break
            elif role == self.rank_roles["2"]:
                rank_role = 2
                break
            elif role == self.rank_roles["3"]:
                rank_role = 3
                break

        if not rank_role:
            raise GameSessionError(f"Member {member.display_name} does not have rank role")

        game_player = GamePlayer(member, member.display_name, rank_role)
        self.ctx.app.game_session_manager.player_cache.set(member.id, game_player)
        return game_player

    async def _get_players(self, members: list[hikari.Member]) -> None:
        """Create GamePlayer objects for this session.

        Parameters
        ----------
        members : list[hikari.Member]
            The list of members to get GamePlayer objects for.

        """
        players: list[GamePlayer] = []

        for member in members:
            cache_result = self._session_manager.player_cache.get(member.id)
            if cache_result:
                players.append(cache_result)
                continue

            players.append(await self._get_player_object(member))

        self._players = players

    def _generate_team_pairs(self) -> list[list[GameTeam]]:
        """Generate 4 pairs of GameTeams where the total skill level of each team is as close as possible.

        Returns
        -------
        list[list[GameTeam]]
            A list of 4 GameTeam pairs.

        """
        assert self.players is not None
        assert len(self.players) == 8

        unique_team_pairs = {}
        results = []

        # Generates all possible 4 player combinations
        for team_a in itertools.combinations(range(8), 4):
            team_a_sorted = tuple(sorted(team_a))
            team_b_sorted = tuple(sorted(set(range(8)) - set(team_a)))

            # Tuple sorting to avoid duplicates
            key = tuple(sorted([team_a_sorted, team_b_sorted]))
            if key in unique_team_pairs:
                continue
            unique_team_pairs[key] = True

            # Gets the total skill for each team
            team_a_skill = sum(self.players[i].role for i in team_a_sorted)
            team_b_skill = sum(self.players[i].role for i in team_b_sorted)
            diff = abs(team_a_skill - team_b_skill)

            results.append(
                {"teams": key, "team_a_skill": team_a_skill, "team_b_skill": team_b_skill, "difference": diff}
            )

        # Sorts the results by team skill diff and takes top four (least diff)
        results.sort(key=lambda r: r["difference"])
        top_four_teams = results[:4]

        teams = []

        # Creates pairs of GameTeams
        for team_pair in top_four_teams:
            team1, team2 = team_pair["teams"]

            team_a_players = [self.players[i] for i in team1]
            team_b_players = [self.players[i] for i in team2]

            team_a = GameTeam(team_a_players, create_team_name(), team_pair["team_a_skill"])
            team_b = GameTeam(team_b_players, create_team_name(), team_pair["team_b_skill"])

            teams.append([team_a, team_b])

        return teams

    async def _do_matchmaking_voting(self, matches: list[list[GameTeam]]) -> list[GameTeam] | None:
        """Start player voting to determine a match.

        Parameters
        ----------
        matches : list[list[hikari.Member]]
            A list of proposed team matches.

        Returns
        -------
        list[GameTeam] | None
            The winning GameTeams or None if no game team is voted for.

        """
        await self.ctx.wait()
        while True:  # lol
            embed = hikari.Embed(
                title="Team Voting",
                description="Vote for your team now below :point_down:",
                colour=DEFAULT_EMBED_COLOUR,
            )

            for i, match in enumerate(matches, 1):
                embed.add_field(
                    name=f"Teams {i}",
                    value=f"**{match[0].name}** - vs - **{match[1].name}**\n"
                    f"{match[0].players[0].name} ({match[0].players[0].role}) - - "
                    f"{match[1].players[0].name} ({match[1].players[0].role})\n"
                    f"{match[0].players[1].name} ({match[0].players[1].role}) - - "
                    f"{match[1].players[1].name} ({match[1].players[1].role})\n"
                    f"{match[0].players[2].name} ({match[0].players[2].role}) - - "
                    f"{match[1].players[2].name} ({match[1].players[2].role})\n"
                    f"{match[0].players[3].name} ({match[0].players[3].role}) - - "
                    f"{match[1].players[3].name} ({match[1].players[3].role})",
                    inline=False,
                )
            embed.set_footer("Waiting for votes... (30sec)")

            winner_vote = await self.ctx.team_vote(edit=True, embed=embed)

            if not winner_vote:
                embed = hikari.Embed(description=f"{FAIL_EMOJI} **No-one voted for a team**", colour=FAIL_EMBED_COLOUR)

                if await self.ctx.retry(author=self.ctx.author.id, edit=True, embed=embed):
                    continue

                return

            return matches[winner_vote - 1]

    async def start(self, members: list[hikari.Member]) -> None:
        """Start this session and listening for interactions.

        Should only be called by a GameSessionManager.

        Parameters
        ----------
        members : list[hikari.Member]
            A list of members that belong to this session (i.e. players)

        """
        await self._session_manager.bind(self.ctx.guild, self)
        self._id = self._session_manager.session_count + 1

        await self._fetch_rank_roles()
        await self._get_players(members)

        proposed_matches = self._generate_team_pairs()
        winning_match = await self._do_matchmaking_voting(proposed_matches)

        if not winning_match:
            return

        embed = hikari.Embed(
            title="Matchmaking complete",
            description=f"**{winning_match[0].name}** (Rank {winning_match[0].skill}) vs "
            f"**{winning_match[1].name}** (Rank {winning_match[1].skill})",
            colour=DEFAULT_EMBED_COLOUR,
        )
        embed.add_field(
            name=winning_match[0].name, value="\n".join(player.name for player in winning_match[0].players), inline=True
        )
        embed.add_field(
            name=winning_match[1].name, value="\n".join(player.name for player in winning_match[1].players), inline=True
        )
        embed.set_footer("Waiting for match score...")

        await self.ctx.edit_last_response(embed=embed, components=[])

        ...  # ToDo


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
