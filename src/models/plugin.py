from __future__ import annotations

import typing as t

if t.TYPE_CHECKING:
    from src.models.bot import BattleFrontBot

import lightbulb


class BattlefrontBotPlugin(lightbulb.Plugin):
    """Plugin subclass for correct subtyping."""

    @property
    def app(self) -> BattleFrontBot:
        return super().app  # type: ignore

    @app.setter
    def app(self, val: BattleFrontBot) -> None:
        self._app = val
        self.create_commands()

    @property
    def bot(self) -> BattleFrontBot:
        return super().app  # type: ignore


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
