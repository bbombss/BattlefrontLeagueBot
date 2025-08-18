__all__ = [
    "DEFAULT_EMBED_COLOUR",
    "FAIL_EMBED_COLOUR",
    "FAIL_EMOJI",
    "GITHUB_LINK",
    "INVITE_LINK_TEMPLATE",
    "LOADING_EMOJI",
    "SUCCESS_EMBED_COLOUR",
    "SUCCESS_EMOJI",
    "TRELLO_LINK",
    "WARN_EMBED_COLOUR",
]

import hikari

DEFAULT_EMBED_COLOUR: hikari.Colour = hikari.Colour(0xD84F00)
SUCCESS_EMBED_COLOUR: hikari.Colour = hikari.Colour(0x0D6623)
WARN_EMBED_COLOUR: hikari.Colour = hikari.Colour(0xAB6B13)
FAIL_EMBED_COLOUR: hikari.Colour = hikari.Colour(0x9C251C)

SUCCESS_EMOJI: str = "<:confirm:1219174344203436042>"
FAIL_EMOJI: str = "<:cancel:1219185372710572092>"
LOADING_EMOJI: str = "<a:loadingbf2:1387019740513308712>"

INVITE_LINK_TEMPLATE: str = "https://discord.com/oauth2/authorize?client_id=1383448316292890745"
GITHUB_LINK: str = "https://github.com/bbombss/BattlefrontLeagueBot"
TRELLO_LINK: str = "https://bbo.ms/bf2bot"


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
