from __future__ import annotations

import hikari
import hikari.guilds
import lightbulb


def is_admin(member: hikari.Member) -> bool:
    """Will return true if a member has the administrator permission.

    Parameters
    ----------
    member : hikari.Member
        The member to check.

    """
    return has_permissions(member, hikari.Permissions(hikari.Permissions.ADMINISTRATOR))


def has_permissions(member: hikari.Member, perms: hikari.Permissions, strict: bool = True) -> bool:
    """Will return true if a member has specified permissions.

    Parameters
    ----------
    member : hikari.Member
        The member to check.
    perms : hikari.Permissions
        The permissions to check for.
    strict : bool
        Whether the member must poses all or at least one of the permissions.
        Defaults to True.

    """
    member_perms: hikari.Permissions = lightbulb.utils.permissions_for(member)

    if member_perms == hikari.Permissions.NONE:
        return False

    if strict and (member_perms & perms) == perms:
        return True

    elif not strict:
        for perm in perms:
            if perm in member_perms:
                return True

    return False


def higher_role(member: hikari.Member, bot: hikari.Member) -> bool:
    """Will return true if the members highest role is higher than the bots.

    Parameters
    ----------
    member : hikari.Member
        The member to check.
    bot : hikari.Member
        The bot member for the relevant server.

    """
    member_role = member.get_top_role()
    bot_role = bot.get_top_role()
    assert member_role is not None
    assert bot_role is not None

    return member_role.position > bot_role.position


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
