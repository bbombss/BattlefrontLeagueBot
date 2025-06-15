__all__ = [
    "GameContext",
    "GameSession"
]

import itertools
import typing as t

import hikari
from random import randint

if t.TYPE_CHECKING:
    from src.models.bot import BattleFrontBot

from src.static import *
from src.models.errors import *


class GamePlayer:
    """Player object for GameSessions."""
    def __init__(self, name: str, role: int) -> None:
        """Player object for GameSessions.

        Parameters
        ----------
        name : str
            The name of this player.
        role : int
            The role rank this player has.

        """
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


class GameContext:
    """Context object for GameSessions."""
    def __init__(self, app: BattleFrontBot, channel: hikari.GuildChannel, author: hikari.Member):
        """Context object for GameSessions.

        Parameters
        ----------
        app : BattleFrontBot
            The app this context is tied to.
        channel : hikari.GuildChannel
            The channel this context was created for.
        author : hikari.Member
            The memeber this context was created for (i.e. the session initiator).

        """
        self.app = app
        self.channel = channel
        self.author = author

    async def respond(self, *args, **kwargs) -> None:
        """Create a response for this context."""
        await self.app.rest.create_message(self.channel, *args, **kwargs)


# ToDo: Rewrite; fix structure
class GameSession:
    """Session object that is used to track game progress and stats."""
    def __init__(self, guild: hikari.Guild, members: list[hikari.Member]) -> None:
        """Session object that is used to track game progress and stats.

        Parameters
        ----------
        guild : hikari.Guild
            The guild this session was created in.
        members : list[hikari.Member]
            A list of members that belong to this session (i.e. players)

        """
        self.guild = guild
        self.members = members

        self.players: list[GamePlayer]
        """List of GamePlayers participating in this session."""

        self.id: int
        """The id of this session."""

        self.ctx: GameContext
        """The game context object for this session."""

    async def get_players(self) -> None:
        """Creates GamePlayers for this session."""
        players: list[GamePlayer] = []

        # ToDo: Temporary lol
        for member in self.members:
            roles = await member.fetch_roles()
            for role in roles:
                if role.name.startswith("Green"):
                    players.append(GamePlayer(member.display_name, 1))
                    break
                elif role.name.startswith("Yellow"):
                    players.append(GamePlayer(member.display_name, 2))
                    break
                elif role.name.startswith("Red"):
                    players.append(GamePlayer(member.display_name, 3))
                    break
                else:
                    raise GameSessionError("Member missing rank role")

        self.players = players

    def create_team_name(self) -> str:
        """Creates a team name from the 2 team seed wordlists."""
        name = (TEAM_NAME_KEY_1[randint(0, len(TEAM_NAME_KEY_1)-1)] +
                TEAM_NAME_KEY_2[randint(0, len(TEAM_NAME_KEY_2)-1)])
        return name

    def generate_teams_pairs(self) -> list[list[GameTeam]]:
        """Generates 4 pairs of GameTeams where the total skill level of each team is as close as possible.

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

            results.append({
                "teams": key,
                "team_a_skill": team_a_skill,
                "team_b_skill": team_b_skill,
                "difference": diff
            })

        # Sorts the results by team skill diff and takes top four (least diff)
        results.sort(key=lambda r: r["difference"])
        top_four_teams = results[:4]

        teams = []

        # Creates pairs of GameTeams
        for team_pair in top_four_teams:
            team1, team2 = team_pair["teams"]

            team_a_players = [self.players[i] for i in team1]
            team_b_players = [self.players[i] for i in team2]

            team_a = GameTeam(team_a_players, self.create_team_name(), team_pair["team_a_skill"])
            team_b = GameTeam(team_b_players, self.create_team_name(), team_pair["team_b_skill"])

            teams.append([team_a, team_b])

        return teams

    async def start(self, ctx: GameContext) -> None:
        """Starts this session and listening for interactions.

        Parameters
        ----------
        ctx : GameContext
            The context object for this session.

        """
        self.ctx = ctx

        self.id = self.ctx.app.game_session_count + 1
        self.ctx.app.game_session_count += 1

        ...  # TODO
