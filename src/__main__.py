import logging
import os
import sys

from src.models import BattleFrontBot

if sys.version_info[0] != 3 or sys.version_info[1] < 12:
    raise RuntimeError("Incompatible python version, must be 3.12 or later.")

try:
    from .config import Config

except ImportError:
    logging.fatal("Config file not found aborting")
    exit(1)

if os.name != "nt":
    try:
        import uvloop  # type: ignore

        uvloop.install()

        logging.info("Running with uvloop event loop")

    except ImportError:
        logging.warning("Failed to import uvloop, running with default async event loop")

bot = BattleFrontBot(Config())

if __name__ == "__main__":
    bot.run()


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
