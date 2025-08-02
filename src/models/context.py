from __future__ import annotations

import typing as t
from abc import ABC

import hikari
import hikari.errors
import lightbulb

if t.TYPE_CHECKING:
    from src.models.bot import BattleFrontBot

from src.models.views import AuthorOnlyNavView, ConfirmationView
from src.static import *

__all__ = ["BattlefrontBotContext", "BattlefrontBotPrefixContext", "BattlefrontBotSlashContext"]


class BattlefrontBotContext(lightbulb.Context, ABC):
    """BBombsBot base context object, abstract class."""

    @property
    def app(self) -> BattleFrontBot:
        """Returns the current application."""
        return super().app  # type: ignore

    async def loading(self) -> lightbulb.ResponseProxy:
        """Create a response with loading a message."""
        return await self.respond(f"{LOADING_EMOJI} Waiting for server...")

    async def respond_with_success(
        self,
        content: str,
        title: str | None = None,
        edit: bool = False,
        ephemeral: bool = False,
    ) -> lightbulb.ResponseProxy:
        """Create a response with a success embed.

        Parameters
        ----------
        content : str
            Content to be passed to the description field of the embed.
        title : str
            Title to be passed to the title field of the embed, defaults to None.
        edit : bool
            Whether an original response should be edited.
        ephemeral : bool
            Whether the message should have the ephemeral flag, defaults to False.

        Returns
        -------
        message : lightbulb.ResponseProxy
            The message that was created as a response.

        """
        embed = hikari.Embed(
            title=title,
            description=f"{SUCCESS_EMOJI} {content}",
            colour=SUCCESS_EMBED_COLOUR,
        )

        flags = hikari.MessageFlag.EPHEMERAL if ephemeral else hikari.MessageFlag.NONE

        assert self.previous_response is not None

        if edit and await self.edit_last_response("", embed=embed, components=[]):
            return self.previous_response

        return await self.respond(embed=embed, flags=flags)

    async def respond_with_failure(
        self,
        content: str,
        title: str | None = None,
        edit: bool = False,
        ephemeral: bool = False,
    ) -> lightbulb.ResponseProxy:
        """Create a response with a failure embed.

        Parameters
        ----------
        content : str
            Content to be passed to the description field of the embed.
        title : str
            Title to be passed to the title field of the embed, defaults to None.
        edit : bool
            Whether an original response should be edited, defaults to False.
        ephemeral : bool
            Whether the message should have the ephemeral flag, defaults to False.

        Returns
        -------
        message : lightbulb.ResponseProxy
            The message that was created as a response.

        """
        embed = hikari.Embed(
            title=title,
            description=f"{FAIL_EMOJI} {content}",
            colour=FAIL_EMBED_COLOUR,
        )

        flags = hikari.MessageFlag.EPHEMERAL if ephemeral else hikari.MessageFlag.NONE

        assert self.previous_response is not None

        if edit and await self.edit_last_response("", embed=embed, components=[]):
            return self.previous_response

        return await self.respond(embed=embed, flags=flags)

    async def get_confirmation(
        self,
        *args,
        confirm_msg: dict[str, t.Any] | None = None,
        cancel_msg: dict[str, t.Any] | None = None,
        timeout: float = 120,
        edit: bool = False,
        **kwargs,
    ) -> bool | None:
        """Prompt the author with a confirmation menu.

        Parameters
        ----------
        confirm_msg : dict[str, Any]
            Keyword arguments to be passed to the confirmation response, defaults to None.
        cancel_msg : dict[str, Any]
            Keyword arguments to be passed to the cancel response, defaults to None.
        timeout : float
            Timeout for confirmation prompt, defaults to 120.
        edit : bool
            Whether the original response should be edited, defaults to False.
        *args : Any
            Arguments passed to the confirmation response.
        **kwargs
            Keyword arguments to be passed to the confirmation response.

        Returns
        -------
        value : bool
            A boolean representing the users response, or none if timeout.

        """
        view = ConfirmationView(self, timeout, confirm_msg, cancel_msg)
        message: hikari.Message | None = None

        if edit:
            message = await self.edit_last_response(*args, components=view, **kwargs)
        if message is None:
            resp = await self.respond(*args, components=view, **kwargs)
            message = await resp.message()

        self.app.miru_client.start_view(view, bind_to=message)
        await view.wait()
        return view.value

    async def respond_paginated(self, pages: list[str], timeout: float = 360, edit: bool = False, **kwargs) -> None:
        """Generate a paginated menu as embeds.

        Parameters
        ----------
        pages : list[str]
            List of pages for the paginator, only supports strings.
        timeout : float
            Timeout for confirmation prompt, defaults to 360.
        edit : bool
            Whether the original response should be edited, defaults to False.
        **kwargs
            Keyword args to be passed to each paginated embed.

        """
        current_page = 1
        page_count = len(pages)
        embed_pages: list[hikari.Embed] = []
        message: hikari.Message | None = None

        for page in pages:
            embed = hikari.Embed(description=page, **kwargs)
            embed.set_footer(f"Page {current_page} of {page_count}")
            embed_pages.append(embed)
            current_page += 1

        if len(embed_pages) < 2:
            raise ValueError("Paginator must have more than one page.")

        navigator = AuthorOnlyNavView(self, embed_pages, timeout=timeout)

        if edit:
            message = await self.edit_last_response("", embeds=[embed_pages[0]], component=navigator)
        if message is None:
            resp = await self.respond("", embeds=[embed_pages[0]], components=navigator)
            message = await resp.message()

        self.app.miru_client.start_view(navigator, bind_to=message)
        await navigator.wait()


class BattlefrontBotApplicationContext(BattlefrontBotContext, lightbulb.ApplicationContext, ABC):
    """BBombsBot ApplicationContext object."""


class BattlefrontBotSlashContext(BattlefrontBotApplicationContext, lightbulb.SlashContext):
    """BBombsBot SlashContext object."""


class BattlefrontBotPrefixContext(BattlefrontBotContext, lightbulb.PrefixContext):
    """BBombsBot SlashContext object."""


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
