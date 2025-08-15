from __future__ import annotations

__all__ = ["GameSession", "SessionContext"]

import asyncio
import datetime
import itertools
import math
import typing as t
from collections import Counter
from io import BytesIO
from random import randint

import hikari

from src.models.database_match import DatabaseMatch
from src.models.database_member import DatabaseMember

if t.TYPE_CHECKING:
    from src.models.bot import BattleFrontBot

from src.models.errors import *
from src.models.views import CapsVotingView, RetryView
from src.static import *
from src.utils import generate_game_banner


def create_team_name() -> str:
    """Create a team name from the 2 team seed wordlists."""
    name = (
        TEAM_NAME_KEY_1[randint(0, len(TEAM_NAME_KEY_1) - 1)]
        + " "
        + TEAM_NAME_KEY_2[randint(0, len(TEAM_NAME_KEY_2) - 1)]
    )
    return name


def ellipsize(s: str, width: int) -> str:
    """Append an ellipse to strings greater than the defined width."""
    if len(s) <= width:
        return s
    return s[: width - 3] + "..."


class GamePlayer:
    """Player object for GameSessions."""

    def __init__(self, member: hikari.Member, name: str, role: int, rank: int, mu: float, sigma: float) -> None:
        """Player object for GameSessions.

        Parameters
        ----------
        member : hikari.Member
            The member that corresponds to this player.
        name : str
            The name of this player.
        role : int
            The role rank this player has.
        rank : int
            The mmr this player has.
        mu : float
            The openscore mu for this player.
        sigma : float
            The operscore sigma for this player.

        """
        self.member = member
        self.name = name
        self.role = role
        self.rank = rank
        self.mu = mu if mu is not None else 25.0
        self.sigma = sigma if sigma is not None else self.mu / 3


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
        self.round1_scores: tuple[int] | None = None
        self.round2_scores: tuple[int] | None = None

        self.winner: GameTeam | None = None
        self.loser: GameTeam | None = None
        self.final_scores: tuple[int] | None = None


def format_team_voting_embed(matches_group: list[GameMatch]) -> tuple[hikari.Embed, list[str]]:
    """Create a formatted embed with the provided matches.

    Parameters
    ----------
    matches_group : list[GameMatch]
       A list of 4 matches for players to vote on.

    Returns
    -------
    tuple[hikari.Embed, list[str]]
        Tuple containing the resulting embed and all it's fields.

    """
    embed = hikari.Embed(
        title="Team Voting",
        description="Vote for your team now below :point_down:",
        colour=DEFAULT_EMBED_COLOUR,
    )

    all_lefts = []
    for match in matches_group:
        for p in match.team1.players:
            all_lefts.append(f"0| {p.name}")

    max_left_width = max(len(s) for s in all_lefts)
    cutoff = min(max_left_width, 24)
    fields = []

    for i, match in enumerate(matches_group, 1):
        lines = []

        for left, right in zip(match.team1.players, match.team2.players):
            left_str = f"{left.role}| {left.name}"
            right_str = f"{right.role}| {right.name}"

            left_trunc = ellipsize(left_str, cutoff).ljust(cutoff)
            right_trunc = ellipsize(right_str, cutoff)
            lines.append(f"{left_trunc} {right_trunc}")

        teams = f"**{match.team1.name}** - vs - **{match.team2.name}**```{'\n'.join(lines)}```"
        embed.add_field(name=f"Teams {i}", value=teams)
        fields.append(teams)

    embed.set_footer("Waiting for votes... (5min)")
    return embed, fields


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

    async def edit_last_response(self, *args, **kwargs) -> hikari.Message:
        """Edit the last response created for this context.

        Will create a new response if there is no previous response.

        Parameters
        ----------
        args : Any
            Arguments passed to the message builder.
        kwargs : Any
            Keyword arguments passed to the message builder.

        Returns
        -------
        hikari.Message | None
            The resulting created or updated message.

        """
        if not self.last_response:
            return await self.respond(*args, **kwargs)

        msg = await self.last_response.edit(*args, **kwargs)
        self._last_response = msg

        return msg

    async def loading(self) -> hikari.Message:
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

    async def team_vote(
        self,
        players: list[hikari.Member],
        embed: hikari.Embed,
        fields: list[str],
        timeout: float = 300,
        edit: bool = False,
    ) -> int | None:
        """Poll players for their team preference and returns the winning vote.

        Parameters
        ----------
        players : list[hikari.Member]
            The players in the teams.
        embed : hikari.Embed
            The team voting embed.
        fields : list[str]
            Each of the fields in the embed.
        timeout : float
            Timeout for view, defaults to 30.
        edit : bool
            Whether the original response should be edited, defaults to False.

        Returns
        -------
        int | None
            Returns the winning vote or None if there were no votes and 5 for a reset.

        """
        view = CapsVotingView(players, embed, fields, author=self.author.id, timeout=timeout)

        if edit:
            msg = await self.edit_last_response("", components=view, embed=embed)
        else:
            msg = await self.respond(components=view, embed=embed)

        self._last_response = msg
        self.app.miru_client.start_view(view, bind_to=msg)
        await view.wait()

        if len(view.votes) < 1:
            return

        vote_counts = Counter(view.votes.values())
        winner_vote, winner_count = vote_counts.most_common(1)[0]
        return winner_vote

    async def send_round_update(self, round_no: int, match: GameMatch, map: str | None = None) -> hikari.Message:
        """Update the round information embed with the latest round information.

        Parameters
        ----------
        round_no : int
            The round number.
        match : GameMatch
            The game match with the latest information.
        map : str | None
            A url to the map for this match or None if there is no map.

        Returns
        -------
        hikari.Message | None
            The resulting created message.

        """
        sides = ["Light", "Dark"] if round_no == 1 else ["Dark", "Light"]

        if match.winner:
            win_title = (
                f"{match.winner.name} Wins: {match.final_scores[0]} - {match.final_scores[1]}"
                if match.final_scores[0] != match.final_scores[1]
                else "Teams Tied"
            )
            win_desc = f"{match.team1.name} ({match.final_scores[0]}) vs {match.team2.name} ({match.final_scores[1]})"

        embed = hikari.Embed(
            title=f"Round {round_no}" if not match.winner else win_title,
            description=f"**{match.team1.name}** (Rank {match.team1.skill}) vs "
            f"**{match.team2.name}** (Rank {match.team2.skill})"
            if not match.winner
            else win_desc,
            colour=DEFAULT_EMBED_COLOUR,
        )
        embed.add_field(
            name=f"{match.team1.name}{f' ({sides[0]} Side)' if not match.winner else ''}",
            value="\n".join(player.name for player in match.team1.players),
            inline=True,
        )
        embed.add_field(
            name=f"{match.team2.name}{f' ({sides[1]} Side)' if not match.winner else ''}",
            value="\n".join(player.name for player in match.team2.players),
            inline=True,
        )
        embed.set_footer("Waiting for scores..." if not match.winner else "Session finished")
        embed.set_image(map)

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

    async def send_match_summary(self, match: GameMatch) -> None:
        """Send a match summary in the context channel.

        Parameters
        ----------
        match : GameMatch
            The completed game match.

        """
        if not match.winner:
            raise GameSessionError("Cannot create a match summary for an incomplete match")

        # Call generate_game_banner on a thread from the existing asyncio pool
        b: BytesIO = await asyncio.get_running_loop().run_in_executor(
            None,
            generate_game_banner,
            [match.team1.name, match.team2.name],
            match.final_scores,
            [player.name for player in match.winner.players],
        )

        await self.app.rest.create_message(
            self.channel,
            f"Congrats {', '.join([player.member.mention for player in match.winner.players])} for winning "
            f"{match.final_scores[0]} - {match.final_scores[1]} against their opponents",
            user_mentions=True,
            attachment=hikari.Bytes(b.getvalue(), "banner.jpg"),
        )


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
        self._rank_roles: dict[int, hikari.Snowflake]
        self._id: int
        self._session_task: asyncio.Task[t.Any] | None = None
        self._session_manager = ctx.app.game_session_manager
        self._latest_score: tuple[int, int] = (0, 0)
        self._match: GameMatch
        self._event = asyncio.Event()
        self._map: str | None = None

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
    def rank_roles(self) -> dict[int, hikari.Snowflake]:
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
            0: hikari.Snowflake(record["rank0role"]),
            1: hikari.Snowflake(record["rank1role"]),
            2: hikari.Snowflake(record["rank2role"]),
            3: hikari.Snowflake(record["rank3role"]),
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
            for i in range(0, 4):
                if role == self.rank_roles[i]:
                    rank_role = i
                    break

        if rank_role is None:
            rank_role = 0
            await self.ctx.warn(
                f"Assigned rank 0 (White) to {member.display_name} because they do not have a rank role"
            )

        db_member = await DatabaseMember.fetch(member.id, member.guild_id)

        game_player = GamePlayer(member, member.display_name, rank_role, db_member.rank, db_member.mu, db_member.sigma)
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

    def _generate_matches(self) -> list[GameMatch]:
        """Generate all possible GameMatches where the total skill level of each team is ordered.

        Returns
        -------
        list[GameMatch]
            A list of GameMatches with team pairs.

        """
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
        await self.ctx.loading()

        total_groups = math.floor(len(matches) / 4)
        round_index = 0

        while True:
            group_start = round_index % total_groups * 4

            embed, fields = format_team_voting_embed(matches[group_start : group_start + 4])
            vote = await self.ctx.team_vote([player.member for player in self._players], embed, fields, edit=True)

            if not vote:
                embed = hikari.Embed(description=f"{FAIL_EMOJI} **No-one voted for a team**", colour=FAIL_EMBED_COLOUR)

                if await self.ctx.retry(author=self.ctx.author.id, edit=True, embed=embed):
                    round_index = 0
                    continue

                self._session_manager.remove_session(self.ctx.guild.id)
                return

            if vote == 5:  # Skip
                round_index += 1
                if round_index > total_groups - 1:
                    round_index = 0
                continue

            winner_index = group_start + (vote - 1)
            return matches[winner_index]

    async def _handle_ranking(self) -> None:
        """Rate the session match with openskill and persist the adjustments.

        This method also logs the adjustments to each member.
        """
        if not self._match.winner:
            raise GameSessionError("Session match must be over to model it in openskill")

        model = self._session_manager.openskill_model
        tied = self._match.final_scores[0] == self._match.final_scores[1]

        winners, losers = [], []
        for member in self._match.winner.players:
            winners.append(model.rating(member.mu, member.sigma, str(member.member.id)))
        for member in self._match.loser.players:
            losers.append(model.rating(member.mu, member.sigma, str(member.member.id)))

        winners, losers = model.rate([winners, losers], ranks=[0, 0] if tied else None)

        async with self.ctx.app.db.pool.acquire() as con:
            for i in range(0, len(winners)):
                await con.execute(
                    """UPDATE members SET mu = $1, sigma = $2 WHERE userId = $3 AND guildId = $4""",
                    winners[i].mu,
                    winners[i].sigma,
                    int(winners[i].name),
                    self.ctx.guild.id,
                )
                await con.execute(
                    """
                    INSERT INTO memberAuditLog (userId, guildId, matchId, won, tied, mu, sigma)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    int(winners[i].name),
                    self.ctx.guild.id,
                    self.id,
                    not tied,
                    tied,
                    winners[i].mu,
                    winners[i].sigma,
                )

                player = self._match.winner.players[i]
                player.mu = winners[i].mu
                player.sigma = winners[i].sigma
                self._session_manager.player_cache.set(player.member.id, player)

            for i in range(0, len(losers)):
                await con.execute(
                    """UPDATE members SET mu = $1, sigma = $2 WHERE userId = $3 AND guildId = $4""",
                    losers[i].mu,
                    losers[i].sigma,
                    int(losers[i].name),
                    self.ctx.guild.id,
                )
                await con.execute(
                    """
                    INSERT INTO memberAuditLog (userId, guildId, matchId, lost, tied, mu, sigma)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    """,
                    int(losers[i].name),
                    self.ctx.guild.id,
                    self.id,
                    not tied,
                    tied,
                    losers[i].mu,
                    losers[i].sigma,
                )

                player = self._match.loser.players[i]
                player.mu = losers[i].mu
                player.sigma = losers[i].sigma
                self._session_manager.player_cache.set(player.member.id, player)

    async def _save_match(self) -> None:
        """Persist the match associated with this session in the database."""
        if not self._match.winner:
            raise GameSessionError("Cannot save a match that isn't complete")

        match = self._match

        db_match = DatabaseMatch(
            self.id,
            self.ctx.guild.id,
            date=datetime.datetime.now(),
            map=self._map,
            tied=match.final_scores[0] == match.final_scores[1],
        )

        winner_index = 0 if match.final_scores[0] > match.final_scores[1] else 1
        loser_index = 1 - winner_index

        winner_data = {
            "name": match.winner.name,
            "playerIds": [player.member.id for player in match.winner.players],
            "round1Score": match.round1_scores[winner_index],
            "round2Score": match.round2_scores[winner_index],
        }
        loser_data = {
            "name": match.loser.name,
            "playerIds": [player.member.id for player in match.loser.players],
            "round1Score": match.round1_scores[loser_index],
            "round2Score": match.round2_scores[loser_index],
        }
        db_match.winner_data = winner_data
        db_match.loser_data = loser_data
        await db_match.update()
        await db_match.update_members()

    async def _wait_for_scores(self) -> None:
        """Start the game loop waiting for scores.

        Can be stopped by clearing session task.
        """
        total_scores = [0, 0]
        round_no: int = 1
        timeout: bool = False

        def update_match_stats() -> GameMatch:
            if round_no == 1:
                return self._match

            score1, score2 = self._latest_score
            winner = self._match.team1 if score1 > score2 else self._match.team2

            total_scores[0] += score1
            total_scores[1] += score2
            setattr(self._match, f"round{round_no - 1}_scores", (score1, score2))
            setattr(self._match, f"round{round_no - 1}_winner", winner)

            if round_no == 3:
                self._match.winner = self._match.team1 if total_scores[0] > total_scores[1] else self._match.team2
                self._match.loser = self._match.team1 if total_scores[0] < total_scores[1] else self._match.team2
                self._match.final_scores = (total_scores[0], total_scores[1])

                if total_scores[0] == total_scores[1]:
                    self._match.winner = self._match.team1
                    self._match.loser = self._match.team2

            return self._match

        # Update loop for scores
        while self.session_task and round_no < 3:
            await self.ctx.send_round_update(round_no, update_match_stats(), map=self._map)

            try:
                self.event.clear()
                await asyncio.wait_for(self.event.wait(), timeout=3600)
            except asyncio.TimeoutError:
                timeout = True
                break

            round_no += 1

        if sum(total_scores) == 0 or not self.session_task:
            embed = hikari.Embed(
                description=f"{FAIL_EMOJI} **Session was ended{' due to a timeout' if timeout else ''}**",
                colour=FAIL_EMBED_COLOUR,
            )
            await self.ctx.edit_last_response(embed=embed, components=[])
            return

        self._session_task = None
        await self.ctx.send_round_update(round_no, update_match_stats(), map=self._map)
        await self._save_match()
        await self._handle_ranking()
        await self.ctx.send_match_summary(self._match)

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

        self._latest_score = (score1, score2)
        self.event.set()

    def set_map(self, map: str) -> None:
        """Add a map to this session.

        Parameters
        ----------
        map : str
            The url for the map to add.

        """
        self._map = map

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

        self._session_manager.player_cache.check_cache(self.ctx.guild.id)
        await self._fetch_rank_roles()
        await self._get_players(members)

        if not force:
            winning_match = await self._do_matchmaking_voting(self._generate_matches())

            if not winning_match:
                return

            self._match = winning_match

        elif force:
            team1 = GameTeam([player for player in self.players[:4]], create_team_name(), 0)
            team2 = GameTeam([player for player in self.players[4:]], create_team_name(), 0)
            self._match = GameMatch(team1, team2)

            await self.ctx.loading()

        self._session_task = asyncio.create_task(self._wait_for_scores())
        await asyncio.wait_for(self._session_task, timeout=3610)

        self._session_manager.remove_session(self.ctx.guild.id)


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
