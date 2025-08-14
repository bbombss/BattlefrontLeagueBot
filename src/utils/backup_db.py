import asyncio
import datetime
import logging
import os
from pathlib import Path

import hikari

from src.config import Config

logger = logging.getLogger(__name__)


async def backup_db() -> hikari.File | None:
    """Create a database backup using pg_dump.

    Returns
    -------
    hikari.File | None
        The created dump file or None if one is not created.

    """
    user = Config.POSTGRES_USER
    db_name = Config.POSTGRES_DB
    host = Config.POSTGRES_HOST
    port = Config.POSTGRES_PORT
    password = Config.POSTGRES_PASSWORD

    base_dir = str(Path(os.path.abspath(__file__)).parents[2])
    if not os.path.isdir(os.path.join(base_dir, "db_backups")):
        os.mkdir(os.path.join(base_dir, "db_backups"))

    now = datetime.datetime.now(datetime.timezone.utc)
    backup_name = f"{now.year}.{now.month}.{now.day}-{now.hour}.{now.minute}-{now.second}.pgdump"
    backup_path = os.path.join(base_dir, "db_backups", backup_name)

    cmd = [
        "pg_dump",
        "-Fc",
        "-c",
        "--quote-all-identifiers",
        "-U",
        user,
        "-h",
        host,
        "-p",
        str(port),
        "-w",
        "-f",
        backup_path,
        db_name,
    ]
    env = {"PGPASSWORD": password}
    if os.name == "nt":
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]

    p = await asyncio.create_subprocess_exec(*cmd, stderr=asyncio.subprocess.PIPE, env=env)

    result = await p.wait()
    stdout, stderr = await p.communicate()

    if result != 0:
        logger.warning(f"Database backup failed:\n{stderr.decode('unicode_escape')}")
        return

    logger.info("A database backup was performed successfully")
    return hikari.File(backup_path)


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
