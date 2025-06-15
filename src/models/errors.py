class ApplicationStateError(Exception):
    """Exception raised when the application is not ready to receive a particular instruction in its current state."""


class DatabaseStateError(Exception):
    """Exception raised when the database is not ready to receive a particular instruction in its current state."""


class DirectMessageFailedError(Exception):
    """Exception raised when a direct message fails to deliver."""


class GameSessionError(Exception):
    """Exception raised when a session is not properly configured."""


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
