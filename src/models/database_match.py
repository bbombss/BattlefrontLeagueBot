from __future__ import annotations

import datetime
import json
import typing as t

import attr
import hikari

from src.models.database import DatabaseModel


@attr.define
class DatabaseMatch(DatabaseModel):
    id: int
    guild_id: hikari.Snowflake | None
    date: datetime.datetime | None = None
    map: str | None = None
    winner_data: dict[str, t.Any] = attr.field(factory=dict)
    loser_data: dict[str, t.Any] = attr.field(factory=dict)
    tied: bool = False

    async def update(self) -> None:
        await self._db.execute(
            """
            INSERT INTO matches (matchId, guildId, winnerData, loserData, matchTied, matchDate, mapName)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (matchId) DO
            UPDATE SET winnerData = $3, loserData = $4, matchTied = $5, matchDate = $6, mapName = $7;
            """,
            self.id,
            self.guild_id,
            self.winner_data,
            self.loser_data,
            self.tied,
            self.date,
            self.map,
        )

    @classmethod
    async def fetch(cls, match_id: int) -> t.Self:
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
