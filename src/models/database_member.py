from __future__ import annotations

import typing as t

import attr
import hikari

from src.models.database import DatabaseModel


@attr.define
class DatabaseMember(DatabaseModel):
    """Dataclass for stored members in the database."""

    id: hikari.Snowflake
    """The ID for this member."""

    guild_id: hikari.Snowflake
    """The guild ID for this member."""

    rank: int = 0
    """The rank of this member."""

    wins: int = 0
    """The amount of wins for this member."""

    loses: int = 0
    """The amount of loses for this member."""

    ties: int = 0
    """The amount of ties for this member."""

    mu: float | None = None
    """The mu value of a player for the purposes of Openskill."""

    sigma: float | None = None
    """The sigma value of a player for the purposes of Openskill."""

    async def update(self) -> None:
        """Update this member or add them if not already stored."""
        await self._db.execute(
            """
            INSERT INTO members (userId, guildId, rank, wins, loses, ties, mu, sigma)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (userId, guildId) DO
            UPDATE SET rank = $3, wins = $4, loses = $5, ties = $6, mu = $7, sigma = $8;
            """,
            int(self.id),
            int(self.guild_id),
            self.rank,
            self.wins,
            self.loses,
            self.ties,
            self.mu,
            self.sigma,
        )

    @classmethod
    async def fetch(
        cls, user: hikari.SnowflakeishOr[hikari.PartialUser], guild: hikari.SnowflakeishOr[hikari.PartialGuild]
    ) -> t.Self:
        """Fetch this user from the database.

        Parameters
        ----------
        user : hikari.Snowflake
            User ID for the member to be fetched.
        guild : hikari.Snowflake
            Guild of the member to be fetched.

        Returns
        -------
        DatabaseMember
            Dataclass for stored member in the database or a default member if no such member exists.

        """
        record = await cls._db.fetchrow(
            "SELECT * FROM members WHERE userId = $1 and guildId = $2", hikari.Snowflake(user), hikari.Snowflake(guild)
        )

        if not record:
            member = cls(hikari.Snowflake(user), hikari.Snowflake(guild))
            return member

        return cls(
            hikari.Snowflake(record["userid"]),
            hikari.Snowflake(record["guildid"]),
            rank=record["rank"],
            wins=record["wins"],
            loses=record["loses"],
            ties=record["ties"],
            mu=float(record["mu"]) if record["mu"] is not None else None,
            sigma=float(record["sigma"]) if record["sigma"] is not None else None,
        )

    async def remove(self) -> None:
        await self._db.execute(
            """
            DELETE FROM members WHERE userId = $1 AND guildId = $2
            """,
            self.id,
            self.guild_id,
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
