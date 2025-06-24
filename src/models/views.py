import typing as t

import hikari
import lightbulb
import miru

from src.static import *
from src.utils import is_admin


class AuthorOnlyView(miru.View):
    """View that can only be interacted with by the interaction author."""

    def __init__(
        self,
        lightbulb_ctx: lightbulb.Context | None,
        *,
        timeout: float = 120,
        autodefer: bool = True,
    ) -> None:
        """View that can only be interacted with by the interaction author.

        Parameters
        ----------
        lightbulb_ctx : lightbulb.Context | None
            The lightbulb context object, to determine original author.
            If no context is provided the view will be interactable by any user.
        timeout : float
            Timeout for view, defaults to 120.
        autodefer : bool
            Whether to defer delayed interaction responses, defaults to true.

        """
        super().__init__(timeout=timeout, autodefer=autodefer)
        self.lightbulb_ctx = lightbulb_ctx

    async def view_check(self, ctx: miru.ViewContext) -> bool:
        if self.lightbulb_ctx and ctx.user.id != self.lightbulb_ctx.author.id:
            await ctx.respond(
                embed=hikari.Embed(
                    title=None,
                    description=f"{FAIL_EMOJI} You cannot interact with this menu.",
                    colour=FAIL_EMBED_COLOUR,
                ),
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return False

        return True


class NavView(miru.View):
    """Navigation menu with iterable pages."""

    def __init__(
        self,
        pages: list[str | hikari.Embed],
        *,
        timeout: float = 360,
        autodefer: bool = True,
    ) -> None:
        """Navigation menu with iterable pages.

        Parameters
        ----------
        pages : list[str | hikari.Embed]
            List of pages for the navigator only supports str or embed navigators.
        timeout : float
            Timeout for view, defaults to 360.
        autodefer : bool
            Whether to defer delayed interaction responses, defaults to true.

        """
        super().__init__(timeout=timeout, autodefer=autodefer)
        if not isinstance(pages, list) or len(pages) < 2:
            raise ValueError(f"Expected list of at least 2 elements for {type(self).__name__}")

        self.pages = pages
        self._current_page = 0

    @property
    def current_page(self) -> int:
        """Current page index the navigator is on."""
        return self._current_page

    def prepare_page(self, page: str | hikari.Embed) -> dict[str, t.Any]:
        """Prepare a page to be sent as a payload."""
        content = page if isinstance(page, str) else ""
        embeds = [page] if isinstance(page, hikari.Embed) else []

        if content == "" and embeds == []:
            raise TypeError(f"Expected list of embeds or strings for {type(self).__name__}")

        payload = {
            "content": content,
            "embeds": embeds,
            "attachments": None,
            "mentions_everyone": False,
            "user_mentions": False,
            "role_mentions": False,
            "components": self,
        }

        return payload

    async def send_page(self, ctx: miru.ViewContext, page_index: int) -> None:
        """Send a new page, replacing the old one."""
        self._current_page = page_index

        for item in self.children:
            item.disabled = False

        if self.current_page == 0:
            self.get_item_by_id("prev").disabled = True
            self.get_item_by_id("first").disabled = True

        if self.current_page == len(self.pages) - 1:
            self.get_item_by_id("next").disabled = True
            self.get_item_by_id("last").disabled = True

        page = self.pages[self.current_page]

        payload = self.prepare_page(page)

        await ctx.edit_response(**payload)

    @miru.button(emoji="⏮️", custom_id="first", style=hikari.ButtonStyle.SECONDARY)
    async def first_button(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        await self.send_page(ctx, 0)

    @miru.button(emoji="⏪", custom_id="prev", style=hikari.ButtonStyle.PRIMARY)
    async def previous_button(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        await self.send_page(ctx, self.current_page - 1)

    @miru.button(emoji="⏩", custom_id="next", style=hikari.ButtonStyle.PRIMARY)
    async def next_button(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        await self.send_page(ctx, self.current_page + 1)

    @miru.button(emoji="⏭️", custom_id="last", style=hikari.ButtonStyle.SECONDARY)
    async def last_button(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        await self.send_page(ctx, len(self.pages) - 1)

    @miru.button(emoji="🗑️", style=hikari.ButtonStyle.DANGER)
    async def delete_button(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        await ctx.message.delete()
        self.stop()

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True

        page = self.pages[self.current_page]

        payload = self.prepare_page(page)

        await self.message.edit(**payload)

        self.stop()


class AuthorOnlyNavView(NavView):
    """Navigator only interactable with by menu author."""

    def __init__(
        self,
        lightbulb_ctx: lightbulb.Context,
        pages: list[str | hikari.Embed],
        *,
        timeout: float = 360,
        autodefer: bool = True,
    ) -> None:
        """Navigator only interactable with by menu author.

        Parameters
        ----------
        lightbulb_ctx : lightbulb.Context
            The lightbulb context object, to determine original author.
        pages : list[str | hikari.Embed]
            List of pages for the navigator only supports str or embed navigators.
        timeout : float
            Timeout for view, defaults to 360.
        autodefer : bool
            Whether to defer delayed interaction responses, defaults to true.

        """
        super().__init__(pages, timeout=timeout, autodefer=autodefer)
        self.lightbulb_ctx = lightbulb_ctx

    async def view_check(self, ctx: miru.ViewContext) -> bool:
        if ctx.user.id != self.lightbulb_ctx.author.id:
            await ctx.respond(
                embed=hikari.Embed(
                    title=None,
                    description=f"{FAIL_EMOJI} You cannot interact with this menu.",
                    colour=FAIL_EMBED_COLOUR,
                ),
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return False

        return True


class ConfirmationView(AuthorOnlyView):
    """View for prompting a user for confirmation."""

    def __init__(
        self,
        lightbulb_ctx: lightbulb.Context | None,
        timeout: float = 120,
        confirm_msg: dict[str, t.Any] | None = None,
        cancel_msg: dict[str, t.Any] | None = None,
    ) -> None:
        """View for prompting a user for confirmation.

        Parameters
        ----------
        lightbulb_ctx : lightbulb.Context | None
            The lightbulb context object, if provided makes the view author only.
        timeout : float
            Timeout for view, defaults to 120.
        confirm_msg : dict[str, t.Any] | None
            The response to be sent if the interaction is confirmed, defaults to None.
        cancel_msg : dict[str, t.Any] | None
            The response to be sent if the interaction is cancelled, defaults to None.

        """
        super().__init__(lightbulb_ctx, timeout=timeout)
        self.confirm_msg = confirm_msg
        self.cancel_msg = cancel_msg
        self.value: bool

    async def deactivate(self, ctx: miru.ViewContext) -> None:
        """Deactivate the view by disabling all buttons."""
        for item in self.children:
            item.disabled = True
        await ctx.edit_response(components=self)

    async def on_timeout(self) -> None:
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(components=self)
        self.stop()

    @miru.button(emoji="✔️", style=hikari.ButtonStyle.SUCCESS)
    async def confirm_button(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        self.value = True
        await self.deactivate(ctx)

        if self.confirm_msg:
            await ctx.respond(**self.confirm_msg)
        self.stop()

    @miru.button(emoji="❌", style=hikari.ButtonStyle.SECONDARY)
    async def cancel_button(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        self.value = False
        await self.deactivate(ctx)

        if self.cancel_msg:
            await ctx.respond(**self.cancel_msg)
        self.stop()


class CapsVotingView(miru.View):
    """View for prompting a users to vote for teams."""

    def __init__(
        self,
        author: hikari.Snowflake | None = None,
        timeout: float = 30,
    ):
        """View for prompting a users to vote for teams.

        Parameters
        ----------
        author : hikari.Snowflake | None
            An author id, if given only the author can override, defaults to None.
        timeout : float
            Timeout for view, defaults to 30.

        """
        super().__init__(timeout=timeout)
        self.author = author
        self.votes: dict[hikari.Snowflake, int] = {}
        self.override: bool = False
        self.overriding_user: hikari.Snowflake

    @miru.button("1", style=hikari.ButtonStyle.PRIMARY)
    async def vote_1(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        if self.override:
            if ctx.user.id == self.overriding_user:
                self.votes[ctx.user.id] = 1
                self.stop()
                return

            await ctx.respond(f"{FAIL_EMOJI} You can no longer vote", flags=hikari.MessageFlag.EPHEMERAL)
            return

        self.votes[ctx.user.id] = 1
        await ctx.respond(f"{SUCCESS_EMOJI} Your vote for team 1 was counted", flags=hikari.MessageFlag.EPHEMERAL)

        if len(self.votes) == 8:
            self.stop()

    @miru.button("2", style=hikari.ButtonStyle.PRIMARY)
    async def vote_2(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        if self.override:
            if ctx.user.id == self.overriding_user:
                self.votes[ctx.user.id] = 2
                self.stop()
                return

            await ctx.respond(f"{FAIL_EMOJI} You can no longer vote", flags=hikari.MessageFlag.EPHEMERAL)
            return

        self.votes[ctx.user.id] = 2
        await ctx.respond(f"{SUCCESS_EMOJI} Your vote for team 2 was counted", flags=hikari.MessageFlag.EPHEMERAL)

        if len(self.votes) == 8:
            self.stop()

    @miru.button("3", style=hikari.ButtonStyle.PRIMARY)
    async def vote_3(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        if self.override:
            if ctx.user.id == self.overriding_user:
                self.votes[ctx.user.id] = 3
                self.stop()
                return

            await ctx.respond(f"{FAIL_EMOJI} You can no longer vote", flags=hikari.MessageFlag.EPHEMERAL)
            return

        self.votes[ctx.user.id] = 3
        await ctx.respond(f"{SUCCESS_EMOJI} Your vote for team 3 was counted", flags=hikari.MessageFlag.EPHEMERAL)

        if len(self.votes) == 8:
            self.stop()

    @miru.button("4", style=hikari.ButtonStyle.PRIMARY)
    async def vote_4(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        if self.override:
            if ctx.user.id == self.overriding_user:
                self.votes[ctx.user.id] = 4
                self.stop()
                return

            await ctx.respond(f"{FAIL_EMOJI} You can no longer vote", flags=hikari.MessageFlag.EPHEMERAL)
            return

        self.votes[ctx.user.id] = 4
        await ctx.respond(f"{SUCCESS_EMOJI} Your vote for team 4 was counted", flags=hikari.MessageFlag.EPHEMERAL)

        if len(self.votes) == 8:
            self.stop()

    @miru.button(emoji="⚖️", style=hikari.ButtonStyle.DANGER)
    async def override(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        if self.author and self.author != ctx.user.id and not is_admin(ctx.member):
            await ctx.respond("You are not allowed to override this action", flags=hikari.MessageFlag.EPHEMERAL)
            return

        if self.override and ctx.user.id == self.overriding_user:
            await ctx.respond(
                f"{FAIL_EMOJI} You are already overriding the votes, vote above to finalise :point_up:",
                flags=hikari.MessageFlag.EPHEMERAL,
            )
            return

        self.override = True
        self.votes.clear()
        self.overriding_user = ctx.user.id
        await ctx.respond(
            "**Overriding Votes:** Vote again now to finalise the teams :point_up:", flags=hikari.MessageFlag.EPHEMERAL
        )

    @miru.button(emoji="🔁", style=hikari.ButtonStyle.DANGER)
    async def regen(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        if self.author and self.author != ctx.user.id and not is_admin(ctx.member):
            await ctx.respond(
                f"{SUCCESS_EMOJI} You are not allowed to override this action", flags=hikari.MessageFlag.EPHEMERAL
            )
            return

        await ctx.respond(
            "**Regenerating teams**\n*Note: You can only regenerate teams 3 times*", flags=hikari.MessageFlag.EPHEMERAL
        )

        self.votes.clear()
        self.votes[ctx.user.id] = 5
        self.stop()


class CapsRegisterView(miru.View):
    """View for prompting users to register for caps."""

    def __init__(
        self,
        embed: hikari.Embed,
        author: hikari.Snowflake | None = None,
        timeout: float = 900,
    ) -> None:
        """View for prompting users to register for caps.

        Parameters
        ----------
        embed : hikari.Embed
            The embed this view is tied to.
        author : hikari.Snowflake | None
            An author id, if given only the author can delete, defaults to None.
        timeout : float
            Timeout for view, defaults to 900.

        """
        super().__init__(timeout=timeout)
        self.embed = embed
        self.author = author
        self.registered_members: list[hikari.Member] = []

    async def on_timeout(self) -> None:
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(components=self)
        self.stop()

    async def update_embed(self) -> None:
        self.embed.add_field(name="Players", value="\n".join([user.display_name for user in self.registered_members]))
        await self.message.edit(embed=self.embed)

    @miru.button(label="Register", style=hikari.ButtonStyle.PRIMARY)
    async def confirm_button(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        if ctx.member in self.registered_members:
            await ctx.respond(
                f"{FAIL_EMOJI} You are already registered for this event", flags=hikari.MessageFlag.EPHEMERAL
            )
            return

        self.registered_members.append(ctx.member)
        await ctx.respond(
            f"{SUCCESS_EMOJI} Thank you for registering :heart_hands:", flags=hikari.MessageFlag.EPHEMERAL
        )

        if len(self.registered_members) > 1:
            self.embed.remove_field(0)
        await self.update_embed()

        if len(self.registered_members) == 8:
            self.stop()

    @miru.button(label="Leave", style=hikari.ButtonStyle.PRIMARY)
    async def leave_button(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        if ctx.member not in self.registered_members:
            await ctx.respond(f"{FAIL_EMOJI} You are not already registered", flags=hikari.MessageFlag.EPHEMERAL)
            return

        self.registered_members.remove(ctx.member)
        await ctx.respond(f"{SUCCESS_EMOJI} You have been removed", flags=hikari.MessageFlag.EPHEMERAL)

        self.embed.remove_field(0)
        if len(self.registered_members) > 1:
            await self.update_embed()
        else:
            await self.message.edit(embed=self.embed)

    @miru.button(emoji="🗑️", style=hikari.ButtonStyle.DANGER)
    async def stop_button(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        if self.author and self.author != ctx.user.id and not is_admin(ctx.member):
            await ctx.respond(
                f"{FAIL_EMOJI} You are not allowed to stop this action", flags=hikari.MessageFlag.EPHEMERAL
            )
            return

        self.stop()


class RetryView(miru.View):
    """View for prompting users to retry and action."""

    def __init__(
        self,
        author: hikari.Snowflake | None = None,
        timeout: float = 60,
    ) -> None:
        """View for prompting users to retry an action.

        Parameters
        ----------
        author : hikari.Snowflake | None
            An author id, if given only the author can retry, defaults to None.
        timeout : float
            Timeout for view, defaults to 60.

        """
        super().__init__(timeout=timeout)
        self.author = author
        self.value = False

    async def deactivate(self) -> None:
        """Deactivate the view by disabling all buttons."""
        for item in self.children:
            item.disabled = True
        await self.message.edit(components=self)

    async def on_timeout(self) -> None:
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(components=self)
        self.stop()

    @miru.button(emoji="🔄", style=hikari.ButtonStyle.PRIMARY)
    async def retry_button(self, ctx: miru.ViewContext, button: miru.Button) -> None:
        if self.author and self.author != ctx.user.id:
            await ctx.respond(
                f"{FAIL_EMOJI} You are not allowed to retry this action", flags=hikari.MessageFlag.EPHEMERAL
            )
            return

        self.value = True
        await self.deactivate()
        self.stop()


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
