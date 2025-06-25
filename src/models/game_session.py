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


class GameMatch:
    """Game Match object for GameSessions."""

    def __init__(self, team1: GameTeam, team2: GameTeam) -> None:
        """Game Match object for GameSessions.

        Parameters
        ----------
        team1 : GameTeam
            The first team in this match.
        team2 : GameTeam
            The second team in this match.

        """
        self.team1 = team1
        self.team2 = team2
        self.round1_winner: GameTeam | None = None
        self.round2_winner: GameTeam | None = None
        self.round1_scores: list[int] | None = None
        self.round2_scores: list[int] | None = None
        self.winner: GameTeam | None = None
        self.final_scores: list[int] | None = None


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

    async def warn(self, content: str) -> hikari.Message:
        """Send a warning message.

        Parameters
        ----------
        content : str
            The content of the warning.

        Returns
        -------
        hikari.Message
            The created message.

        """
        embed = hikari.Embed(description=f":warning: **Warning:** {content}", colour=WARN_EMBED_COLOUR)
        return await self.app.rest.create_message(self.channel, embed=embed)

    async def retry(
        self, *args, author: hikari.Snowflake | None = None, timeout: float = 60, edit: bool = False, **kwargs
    ) -> bool:
        """Create a response prompting users to retry.

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

    async def team_vote(self, timeout: float = 300, edit: bool = False, **kwargs) -> int | None:
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
            Returns the winning vote or None if there were no votes and 5 for a reset.

        """
        view = CapsVotingView(author=self.author.id, timeout=timeout)

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

    async def update_round(self, round_no: int, match: GameMatch) -> hikari.Message:
        """Update the round information embed with the latest round information.

        Parameters
        ----------
        round_no : int
            The round number.
        match : GameMatch
            The game match with the latest information.

        Returns
        -------
        hikari.Message | None
            The resulting created message.

        """
        sides = ["Light", "Dark"]

        if round_no == 3:
            win_title = (
                f"{match.winner.name} Wins: {match.final_scores[0]} - {match.final_scores[1]}"
                if match.final_scores[0] != match.final_scores[1]
                else "Teams Tied"
            )
            win_desc = f"{match.team1.name} ({match.final_scores[0]}) vs {match.team2.name} ({match.final_scores[1]})"

        embed = hikari.Embed(
            title=f"Round {round_no}" if round_no < 3 else win_title,
            description=f"**{match.team1.name}** (Rank {match.team1.skill}) vs "
            f"**{match.team2.name}** (Rank {match.team2.skill})"
            if round_no < 3
            else win_desc,
            colour=DEFAULT_EMBED_COLOUR,
        )
        embed.add_field(
            name=f"{match.team1.name}{f' ({sides[0] if round_no == 1 else sides[1]} Side)' if round_no < 3 else ''}",
            value="\n".join(player.name for player in match.team1.players),
            inline=True,
        )
        embed.add_field(
            name=f"{match.team2.name}{f' ({sides[1] if round_no == 1 else sides[0]} Side)' if round_no < 3 else ''}",
            value="\n".join(player.name for player in match.team2.players),
            inline=True,
        )
        embed.set_footer("Waiting for scores..." if round_no < 3 else "Session finished")

        if match.round1_winner:
            if match.round1_scores[0] == match.round1_scores[1]:
                winning_msg = "Teams Tied"
            else:
                winning_msg = f"{match.round1_winner.name} Wins"

            embed.add_field(
                name="Round 1",
                value=f"**{winning_msg}**\n{match.round1_scores[0]} - {match.round1_scores[1]}",
                inline=False,
            )

        if match.round2_winner:
            if match.round2_scores[0] == match.round2_scores[1]:
                winning_msg = "Teams Tied"
            else:
                winning_msg = f"{match.round2_winner.name} Wins"

            embed.add_field(
                name="Round 2",
                value=f"**{winning_msg}**\n{match.round2_scores[0]} - {match.round2_scores[1]}",
                inline=False,
            )

        return await self.edit_last_response("", embed=embed, components=[])


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
        self._session_task: asyncio.Task[t.Any] | None = None
        self._session_manager = ctx.app.game_session_manager
        self._latest_score: dict[GameTeam, int]
        self._match: GameMatch
        self._event = asyncio.Event()

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

    @property
    def event(self) -> asyncio.Event:
        """The event that signals an update and progresses the game loop."""
        return self._event

    @property
    def session_task(self) -> asyncio.Task | None:
        """The task that runs the game loop or None if the game loop isn't running."""
        return self._session_task

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
            A GamePlayer object that corresponds to the member.

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
            rank_role = 1
            await self.ctx.warn(f"Assigned rank 1 to {member.display_name} because they do not have a rank role")

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
            cache_result = self._session_manager.player_cache.get(member.id, member.guild_id)
            if cache_result:
                players.append(cache_result)
                continue

            players.append(await self._get_player_object(member))

        self._players = players

    def _generate_team_pairs(self) -> list[GameMatch]:
        """Generate all possible GameMatches where the total skill level of each team is ordered.

        Returns
        -------
        list[GameMatch]
            A list of GameMatches with team pairs.

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

        teams = []

        # Creates pairs of GameTeams
        for team_pair in results:
            team1, team2 = team_pair["teams"]

            team_a_players = [self.players[i] for i in team1]
            team_b_players = [self.players[i] for i in team2]

            team_a = GameTeam(team_a_players, create_team_name(), team_pair["team_a_skill"])
            team_b = GameTeam(team_b_players, create_team_name(), team_pair["team_b_skill"])

            teams.append(GameMatch(team_a, team_b))

        return teams

    async def _do_matchmaking_voting(self, matches: list[GameMatch]) -> GameMatch | None:
        """Start player voting to determine a match.

        Parameters
        ----------
        matches : list[GameMatch]
            A list of proposed matches.

        Returns
        -------
        GameMatch | None
            The winning GameMatch or None if no match is voted for.

        """
        await self.ctx.wait()
        iter = 0
        matches_groups = [matches[:4], matches[4:8], matches[8:12], matches[12:16]]

        while True:  # lol
            iter += 1
            match_index = iter - 1 if iter < 5 else 3

            embed = hikari.Embed(
                title="Team Voting",
                description="Vote for your team now below :point_down:",
                colour=DEFAULT_EMBED_COLOUR,
            )

            for i, match in enumerate(matches_groups[match_index], 1):
                embed.add_field(
                    name=f"Team {i}",
                    value=f"**{match.team1.name}** - vs - **{match.team2.name}**\n"
                    f"{match.team1.players[0].name} ({match.team1.players[0].role}) - - "
                    f"{match.team2.players[0].name} ({match.team2.players[0].role})\n"
                    f"{match.team1.players[1].name} ({match.team1.players[1].role}) - - "
                    f"{match.team2.players[1].name} ({match.team2.players[1].role})\n"
                    f"{match.team1.players[2].name} ({match.team1.players[2].role}) - - "
                    f"{match.team2.players[2].name} ({match.team2.players[2].role})\n"
                    f"{match.team1.players[3].name} ({match.team1.players[3].role}) - - "
                    f"{match.team2.players[3].name} ({match.team2.players[3].role})",
                    inline=False,
                )
            embed.set_footer("Waiting for votes... (5min)")

            winner_vote = await self.ctx.team_vote(edit=True, embed=embed)

            if not winner_vote:
                self._session_manager._sessions.pop(self.ctx.guild.id)
                embed = hikari.Embed(description=f"{FAIL_EMOJI} **No-one voted for a team**", colour=FAIL_EMBED_COLOUR)

                if iter > 5:
                    await self.ctx.edit_last_response(embed=embed, components=[])
                    return

                if await self.ctx.retry(author=self.ctx.author.id, edit=True, embed=embed):
                    self._session_manager._sessions[self.ctx.guild.id] = self
                    continue

                return

            if winner_vote == 5:
                continue

            return matches[((winner_vote + (4 * (iter - 1))) - 1)]

    async def _wait_for_scores(self) -> None:
        """Start the game loop waiting for scores.

        Can be stopped by clearing session task.
        """
        team1, team2 = self._match.team1, self._match.team2
        team1_score, team2_score = 0, 0
        round_no: int = 0
        timeout: bool = False

        # Update loop for scores
        while self.session_task:
            round_no += 1

            if round_no == 3:
                self._session_task = None
                break

            if round_no == 2:
                team1_score += self._latest_score[0]
                team2_score += self._latest_score[1]

                self._match.round1_winner = team1 if self._latest_score[0] > self._latest_score[1] else team2
                self._match.round1_scores = [self._latest_score[0], self._latest_score[1]]

            await self.ctx.update_round(round_no, self._match)

            self.event.clear()
            try:
                await asyncio.wait_for(self.event.wait(), timeout=3000)
            except asyncio.TimeoutError:
                timeout = True
                self._session_task = None
                break

        # Check if rounds were completed
        if sum([team1_score, team2_score]) == 0 or round_no < 3:
            self._session_manager._sessions.pop(self.ctx.guild.id)
            embed = hikari.Embed(
                description=f"{FAIL_EMOJI} **Session was ended{' due to a timeout' if timeout else ''}**",
                colour=FAIL_EMBED_COLOUR,
            )
            await self.ctx.edit_last_response(embed=embed, components=[])
            return

        team1_score += self._latest_score[0]
        team2_score += self._latest_score[1]
        winning_team = team1 if team1_score > team2_score else team2

        self._match.round2_winner = team1 if self._latest_score[0] > self._latest_score[1] else team2
        self._match.round2_scores = [self._latest_score[0], self._latest_score[1]]
        self._match.winner = winning_team
        self._match.final_scores = [team1_score, team2_score]

        await self.ctx.update_round(round_no, self._match)

        self._session_manager._sessions.pop(self.ctx.guild.id)

        # Update db
        query = """
        WITH new_members AS (
        SELECT unnest($1::bigint[]) AS user_id,
               unnest($2::bigint[]) AS guild_id
        )
        INSERT INTO members (userId, guildId, rank, wins, loses, ties)
        SELECT user_id, guild_id, 0, {0}, {1}, {2}
        FROM new_members
        ON CONFLICT (userId, guildId)
        DO UPDATE SET {3} = members.{3} + 1;
        """

        if team1_score != team2_score:
            loser = team1 if team1_score < team2_score else team2
            winner_ids = [player.member.id for player in winning_team.players]
            loser_ids = [player.member.id for player in loser.players]
            guild_ids = [self.ctx.guild.id] * 4

            await self.ctx.app.db.execute(query.format(*["1", "0", "0", "wins"]), winner_ids, guild_ids)
            await self.ctx.app.db.execute(query.format(*["0", "1", "0", "loses"]), loser_ids, guild_ids)

        else:
            player_ids = [player.member.id for player in [*team1.players, *team2.players]]
            guild_ids = [self.ctx.guild.id] * 8

            await self.ctx.app.db.execute(query.format(*["0", "0", "1", "ties"]), player_ids, guild_ids)

    def add_score(self, score1: int, score2: int) -> None:
        """Add a score to this session.

        Parameters
        ----------
        score1 : int
            The score for the first team.
        score2 : int
            The score for the second team.

        """
        if not self.session_task:
            raise GameSessionError("Session is not ready to receive scores")

        self._latest_score = [score1, score2]
        self.event.set()

    def end(self) -> None:
        """End the game loop."""
        self._session_task = None
        self._event.set()

    async def start(self, members: list[hikari.Member], force: bool = False) -> None:
        """Start this session and listening for interactions.

        Parameters
        ----------
        members : list[hikari.Member]
            A list of members that belong to this session (i.e. players)
        force : bool
            Whether a set of teams is being forced, defaults to False

        """
        self._id = self._session_manager.session_count

        await self._fetch_rank_roles()
        await self._get_players(members)

        if not force:
            proposed_matches = self._generate_team_pairs()
            winning_match = await self._do_matchmaking_voting(proposed_matches)

            if not winning_match:
                return

            self._match = winning_match
        elif force:
            team1 = GameTeam([player for player in self.players[:4]], create_team_name(), 0)
            team2 = GameTeam([player for player in self.players[4:]], create_team_name(), 0)
            self._match = GameMatch(team1, team2)

            await self.ctx.wait()

        self._latest_score = [0, 0]

        self._session_task = asyncio.create_task(self._wait_for_scores())


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
