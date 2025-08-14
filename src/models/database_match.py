from __future__ import annotations

import datetime
import json
import typing as t

import attr
import hikari

from src.models.database import DatabaseModel
from src.models.errors import GameSessionError


@attr.define
class DatabaseMatch(DatabaseModel):
    """Dataclass for stored matches in the database."""

    id: int
    """The ID for this match."""

    guild_id: hikari.Snowflake | None
    """The id of the guild this match was created in."""

    date: datetime.datetime | None = None
    """The date at which this match was completed."""

    map: str | None = None
    """The map that is associated with this match."""

    winner_data: dict[str, t.Any] = attr.field(factory=dict)
    """Data for the winner of this match, must be json serializable."""

    loser_data: dict[str, t.Any] = attr.field(factory=dict)
    """Data for the loser of this match, must be json serializable."""

    tied: bool = False
    """Whether or not this match resulted in a tie."""

    async def update(self) -> None:
        """Update this match or add it if not already stored."""
        await self._db.execute(
            """
            INSERT INTO matches (matchId, guildId, winnerData, loserData, matchTied, matchDate, mapName)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (matchId) DO
            UPDATE SET winnerData = $3, loserData = $4, matchTied = $5, matchDate = $6, mapName = $7;
            """,
            self.id,
            self.guild_id,
            json.dumps(self.winner_data),
            json.dumps(self.loser_data),
            self.tied,
            self.date,
            self.map,
        )

    @classmethod
    async def fetch(cls, match_id: int) -> t.Self:
        """Fetch this match from the database.

        Parameters
        ----------
        match_id : int
            User ID for the match to be fetched.

        Returns
        -------
        DatabaseMatch
            Dataclass for stored match in the database or a default match if no such match exists.

        """
        record = await cls._db.fetchrow("SELECT * FROM matches WHERE matchId = $1", match_id)

        if not record:
            return cls(match_id, None)

        return cls(
            match_id,
            hikari.Snowflake(record["guildid"]),
            date=record["matchdate"],
            map=record["mapname"],
            winner_data=json.loads(record["winnerdata"]),
            loser_data=json.loads(record["loserdata"]),
            tied=record["matchtied"],
        )

    async def update_members(self) -> None:
        """Update the individual players of this match based on the match results."""
        if not self.winner_data or not self.loser_data:
            raise GameSessionError("Cannot update members without match results")

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

        if self.tied:
            all_player_ids = [*self.winner_data["playerIds"], *self.loser_data["playerIds"]]
            await self._db.execute(query.format(*["0", "0", "1", "ties"]), all_player_ids, [self.guild_id] * 8)
            return

        await self._db.execute(
            query.format(*["1", "0", "0", "wins"]), self.winner_data["playerIds"], [self.guild_id] * 4
        )
        await self._db.execute(
            query.format(*["0", "1", "0", "loses"]), self.loser_data["playerIds"], [self.guild_id] * 4
        )


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
