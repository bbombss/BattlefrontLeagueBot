import asyncio
import traceback
from contextlib import redirect_stdout
from io import StringIO
from textwrap import indent
from time import perf_counter_ns

import hikari
import lightbulb

from src.models import (
    BattleFrontBot,
    BattlefrontBotPlugin,
    BattlefrontBotPrefixContext,
)
from src.static import *

admin = BattlefrontBotPlugin("admin")
admin.add_checks(lightbulb.owner_only)


async def respond_paginated(
    ctx: BattlefrontBotPrefixContext,
    content: str,
    prefix: str = "",
    suffix: str = "",
    **kwargs,
) -> None:
    """Responds with interactable paginator.

    Parameters
    ----------
    ctx : BattlefrontBotPrefixContext
        Context for this response.
    content : str
        The text to be paginated, if necessary.
    prefix : str
        Prefix to be added to beginning of each page, defaults to "".
    suffix : str
        Suffix to be added to end of each page, defaults to "".
    **kwargs
        Keywords args to be passed to generated embed(s).

    """
    if "colour" not in kwargs:
        kwargs["colour"] = DEFAULT_EMBED_COLOUR

    if not len(content) > 2000:
        embed = hikari.Embed(description=f"{prefix}{content}{suffix}", **kwargs)
        await ctx.edit_last_response("", embed=embed)
        return

    paginator = lightbulb.utils.StringPaginator(prefix=prefix, suffix=suffix, max_chars=2000)

    for line in content.split("\n"):
        paginator.add_line(line)

    pages = list(paginator.build_pages())

    await ctx.respond_paginated(pages, edit=True, **kwargs)


async def handle_exception(ctx, error: Exception) -> None:
    """Will format exception and respond to original context.

    Parameters
    ----------
    ctx : BattlefrontBotPrefixContext
        Context for this response.
    error : Exception
        The exception to handle

    """
    title = f"{FAIL_EMOJI} {error.__class__.__name__}: {error}"
    content = "\n".join(traceback.format_exception(type(error), error, error.__traceback__))

    await respond_paginated(ctx, content, "```py\n", "```", title=title, colour=FAIL_EMBED_COLOUR)


@admin.command
@lightbulb.option("extension", "Extension to load")
@lightbulb.command("load", "Loads extension", pass_options=True)
@lightbulb.implements(lightbulb.PrefixCommand)
async def ext_load(ctx: BattlefrontBotPrefixContext, extension: str) -> None:
    ctx.app.load_extensions(extension)
    await ctx.respond_with_success(f"**Loaded {extension}**")


@admin.command
@lightbulb.option("extension", "Extension to reload")
@lightbulb.command("reload", "Reloads extension", pass_options=True)
@lightbulb.implements(lightbulb.PrefixCommand)
async def ext_reload(ctx: BattlefrontBotPrefixContext, extension: str) -> None:
    ctx.app.reload_extensions(extension)
    await ctx.respond_with_success(f"**Reloaded {extension}**")


@admin.command
@lightbulb.option("extension", "Extension to unload")
@lightbulb.command("unload", "Unloads extension", pass_options=True)
@lightbulb.implements(lightbulb.PrefixCommand)
async def ext_unload(ctx: BattlefrontBotPrefixContext, extension: str) -> None:
    ctx.app.unload_extensions(extension)
    await ctx.respond_with_success(f"**Unloaded {extension}**")


@admin.command
@lightbulb.command("sync", "Sync application commands")
@lightbulb.implements(lightbulb.PrefixCommand)
async def sync_commands(ctx: BattlefrontBotPrefixContext) -> None:
    await ctx.wait()
    await ctx.app.sync_application_commands()
    await ctx.respond_with_success("**Synced application commands**", edit=True)


@admin.command
@lightbulb.option("messageid", "Message id")
@lightbulb.command("stopview", "Stop a view bound to a message", pass_options=True)
@lightbulb.implements(lightbulb.PrefixCommand)
async def stop_view(ctx: BattlefrontBotPrefixContext, messageid: str) -> None:
    await ctx.wait()

    try:
        id = int(messageid)
    except ValueError:
        await ctx.respond_with_failure("**Invalid message id provided**", edit=True)
        return

    view = ctx.app.miru_client.get_bound_view(id)
    if view is None:
        await ctx.respond_with_failure("**No component found at provided message**", edit=True)
        return

    view.stop()

    await ctx.respond_with_success("**Stopped the view**", edit=True)


@admin.command
@lightbulb.option(
    "code",
    "Code to run, overridden by attached file.",
    required=False,
    modifier=lightbulb.OptionModifier.CONSUME_REST,
)
@lightbulb.command("sql", "Execute sql command from message or file.", pass_options=True)
@lightbulb.implements(lightbulb.PrefixCommand)
async def eval_sql(ctx: BattlefrontBotPrefixContext, code: str) -> None:
    await ctx.wait()

    if ctx.attachments and ctx.attachments[0].filename.endswith(".sql"):
        sql = (await ctx.attachments[0].read()).decode()
    elif code:
        sql = code.replace("```sql", "").replace("`", "").strip()
    else:
        await ctx.respond_with_failure("**Could not find attached file or sql in message**", edit=True)
        return

    output = await ctx.app.db.execute(sql)
    await ctx.respond_with_success(f"**SQL command executed:**\n\n```{output}```", edit=True)


@admin.command
@lightbulb.option("code", "Code to run.", modifier=lightbulb.OptionModifier.CONSUME_REST)
@lightbulb.command("eval", "Evaluate python code.", pass_options=True)
@lightbulb.implements(lightbulb.PrefixCommand)
async def eval_python(ctx: BattlefrontBotPrefixContext, code: str) -> None:
    await ctx.wait()

    globals_env = {
        "ctx": ctx,
        "app": ctx.app,
        "guild": ctx.get_guild(),
        "channel": ctx.get_channel(),
        "author": ctx.author,
        "message": ctx.event.message,
    }

    code = code.replace("```py", "").replace("`", "").strip()

    to_eval = f"async def foo():\n{indent(code, ' ')}"

    try:
        exec(to_eval, globals_env)

    except Exception as error:
        await handle_exception(ctx, error)
        return

    foo = globals_env["foo"]

    f = StringIO()
    try:
        with redirect_stdout(f):
            exec_start = perf_counter_ns()
            try:
                await asyncio.wait_for(foo(), timeout=5)
            except asyncio.TimeoutError:
                await ctx.respond_with_failure("Execution timed out.", edit=True)
                return
            exec_end = perf_counter_ns()

    except Exception as error:
        await handle_exception(ctx, error)
        return

    result = f.getvalue()
    exec_time = f"{(exec_end - exec_start) / 1000000:,.2f}ms"

    if result:
        await respond_paginated(
            ctx,
            result,
            "```py\n",
            "```",
            title=f"{SUCCESS_EMOJI} Evaluated successfully ({exec_time})",
            colour=SUCCESS_EMBED_COLOUR,
        )
    else:
        await ctx.respond_with_success(f"**Evaluated successfully** ({exec_time})", edit=True)


@admin.command()
@lightbulb.command("shutdown", "Shutdown the bot")
@lightbulb.implements(lightbulb.PrefixCommand)
async def shutdown_bot(ctx: BattlefrontBotPrefixContext) -> None:
    confirm_msg = {
        "embed": hikari.Embed(
            title=None,
            description="⚠️ **Shutting down...**",
            colour=WARN_EMBED_COLOUR,
        )
    }
    cancel_msg = {
        "embed": hikari.Embed(
            title=None,
            description=f"{FAIL_EMOJI} **Shutdown cancelled**",
            colour=FAIL_EMBED_COLOUR,
        )
    }

    confirmation = await ctx.get_confirmation(
        "Are you sure you want to shut down BBombsBot, this cannot be undone?",
        confirm_msg=confirm_msg,
        cancel_msg=cancel_msg,
    )

    if confirmation:
        await ctx.app.close()
        return


def load(bot: BattleFrontBot) -> None:
    bot.add_plugin(admin)


def unload(bot: BattleFrontBot) -> None:
    bot.remove_plugin(admin)


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
