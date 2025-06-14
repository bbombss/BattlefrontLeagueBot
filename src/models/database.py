from __future__ import annotations

import abc
import importlib
import logging
import os
import typing as t

import aiofiles
import asyncpg
import hikari

if t.TYPE_CHECKING:
    from src.models.bot import BattleFrontBot

from src.config import Config
from src.models.errors import DatabaseStateError

logger = logging.getLogger(__name__)


class Database:
    """Database class which implements asyncpg to access postgresql database."""

    def __init__(self, app) -> None:
        self._app: BattleFrontBot = app
        self._db_name: str = Config.POSTGRES_DB
        self._user: str = Config.POSTGRES_USER
        self._host: str = Config.POSTGRES_HOST
        self._port: int = Config.POSTGRES_PORT
        self._password: str = Config.POSTGRES_PASSWORD
        self._version: int = Config.POSTGRES_VERSION
        self._pool: asyncpg.Pool | None = None
        self._pool_closed: bool = False
        self._schema_version: int
        self._migrations_dir: str = os.path.join(self._app.base_dir, "src", "sql", "migrations")

        DatabaseModel._db = self
        DatabaseModel._app = self.app

    @property
    def app(self) -> BattleFrontBot:
        """Returns the current application."""
        return self._app

    @property
    def db_name(self) -> str:
        """Returns the connected database name."""
        return self._db_name

    @property
    def user(self) -> str:
        """Returns current database user's username."""
        return self._user

    @property
    def host(self) -> str:
        """Returns the hostname of the database connection."""
        return self._host

    @property
    def port(self) -> int:
        """Returns the port the database is listening on."""
        return self._port

    @property
    def password(self) -> str:
        """Returns the password used to authenticate."""
        return self._password

    @property
    def version(self) -> int:
        """Returns the postgresql version."""
        return self._version

    @property
    def pool(self) -> asyncpg.Pool:
        """Returns the async connection pool."""
        if self._pool is None:
            raise DatabaseStateError("Database is not ready")

        return self._pool

    @property
    def dsn(self) -> str:
        """Returns the url used to connect to the database."""
        return f"postgres://{self.user}:{self.password}@{self.host}:{self.port}/{self.db_name}"

    async def connect(self) -> None:
        """Connect to the database and create a connection pool."""
        if self._pool_closed:
            raise DatabaseStateError("Database pool has been closed")

        self._pool = await asyncpg.create_pool(dsn=self.dsn)
        await self.compile_schema()
        self._schema_version = await self.pool.fetchval("SELECT schemaVersion FROM databaseSchema", column=0)

    async def execute(self, query: str, *args) -> str:
        """Execute a command on the database server.

        Parameters
        ----------
        query : str
            Query to execute.
        args : Tuple[arg]
            Arguments to passed query.

        Returns
        -------
        output : str
            Output from the executed command.

        """
        return await self.pool.execute(query, *args)

    async def fetch(self, query: str, *args) -> list[asyncpg.Record]:
        """Execute an SQL Query and get the returned rows in a list.

        Parameters
        ----------
        query : str
            Query to execute.
        args : Tuple[arg]
            Arguments to passed query.

        Returns
        -------
        records : List[asyncpg.Record]
            Results of the query returned as a list of records.

        """
        return await self.pool.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> asyncpg.Record:
        """Execute an SQL Query and get the returned row.

        Parameters
        ----------
        query : str
            Query to execute.
        args : Tuple[arg]
            Arguments to passed query.

        Returns
        -------
        record : asyncpg.Record
            Results of the query returned as a record.

        """
        return await self.pool.fetchrow(query, *args)

    async def fetchval(self, query: str, *args, column: int = 0) -> t.Any:
        """Execute an SQL Query and get the returned record.

        Parameters
        ----------
        query : str
            Query to execute.
        args : Tuple[arg]
            Arguments to passed query.
        column : int
            Column to return, defaults to 0.

        Returns
        -------
        record
            Resulting value of the query.

        """
        return await self.pool.fetchval(query, *args, column=column)

    async def compile_schema(self) -> None:
        """Create necessary database tables if not already present."""
        async with (
            self.pool.acquire() as con,
            aiofiles.open(os.path.join(self._app.base_dir, "src", "sql", "schema.sql")) as f,
        ):
            await con.execute(await f.read())

    async def increment_schema_version(self) -> None:
        """Increment the current schema version."""
        version = await self.fetchrow(
            """UPDATE databaseSchema SET schemaVersion = schemaVersion + 1
            RETURNING schemaVersion"""
        )

        self._schema_version = version["schemaversion"]
        logger.info(f"Schema updated to version {self._schema_version}")

    async def do_sql_migration(self, file: str) -> None:
        """Execute an SQL file as apart of a database migration."""
        async with aiofiles.open(os.path.join(self._migrations_dir, file)) as f:
            await self.execute(await f.read())

        logger.info(f"Updated database schema with migration {file}")
        await self.increment_schema_version()

    async def do_python_migration(self, file: str) -> None:
        """Execute a python file as apart of a database migration.

        Should have a run method which takes the Database class as a parameter.
        """
        module = importlib.import_module(f"sql.migrations.{file[:-3]}")
        await module.run(self)

        logger.info(f"Updated database schema with migration {file}")
        await self.increment_schema_version()

    async def migrate_schema(self) -> None:
        """Update the database schema with pending migrations."""
        await self.compile_schema()

        async with self.pool.acquire() as con:
            version = await con.fetchval("SELECT schemaVersion FROM databaseSchema", column=0)
            if not isinstance(version, int):
                raise ValueError(f"Expected int for schema version, not {version}")

            self._schema_version = version

        for file in os.listdir(self._migrations_dir):
            try:
                if file.startswith("migration_") and int(file[10]) > self._schema_version:
                    if file.endswith(".sql"):
                        await self.do_sql_migration(file)
                    elif file.endswith(".py"):
                        await self.do_python_migration(file)

            except ValueError:
                logger.warning("Migration filenames must include a version e.g. 'migration_1.sql'")

    async def add_guild(self, guild: hikari.Snowflake) -> None:
        """Add a new guild to the database (does nothing on conflict).

        Parameters
        ----------
        guild : hikari.Snowflake
            Guild to add.

        """
        await self.execute(
            """INSERT INTO guilds (guildId) VALUES ($1)
            ON CONFLICT (guildId) DO NOTHING""",
            guild,
        )

    async def remove_guild(self, guild: hikari.Snowflake) -> None:
        """Remove a guild and all associated data from the database.

        Parameters
        ----------
        guild : hikari.Snowflake
            Guild to remove.

        """
        await self.execute("DELETE FROM guilds WHERE guildId = $1", guild)

    async def close(self) -> None:
        """Close current connection pool."""
        if self._pool_closed:
            raise DatabaseStateError("Database pool is already closed")

        await self.pool.close()
        self._pool_closed = True

    async def terminate(self) -> None:
        """Terminate current connection pool."""
        if self._pool_closed:
            raise DatabaseStateError("Database pool is already closed")

        self.pool.terminate()
        self._pool_closed = True


class DatabaseModel(abc.ABC):
    _db: Database
    _app: BattleFrontBot


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
