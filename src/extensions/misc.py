import datetime
from time import perf_counter_ns

import hikari
import lightbulb
import psutil

from src.models import (
    BattleFrontBot,
    BattlefrontBotPlugin,
    BattlefrontBotSlashContext,
)
from src.static.const import *

misc = BattlefrontBotPlugin("misc")

psutil.cpu_percent(interval=1)


@misc.command
@lightbulb.add_cooldown(1, 10, lightbulb.buckets.UserBucket)
@lightbulb.command("info", description="Get performance statistics for the bot")
@lightbulb.implements(lightbulb.SlashCommand)
async def bot_info(ctx: BattlefrontBotSlashContext) -> None:
    start = perf_counter_ns()
    await ctx.wait()
    end = perf_counter_ns()

    tdelta = datetime.datetime.now() - ctx.app.start_time
    tdelta_str = str(tdelta).split(".")[0].split(":")

    me = ctx.app.get_me()
    assert me is not None

    process = psutil.Process()
    gateway_latency = f"{ctx.app.heartbeat_latency * 1000:,.0f}ms"

    await ctx.edit_last_response(
        "",
        embed=hikari.Embed(
            title=f"{me.username} Info",
            description=f"""Version: **{ctx.app.version}**
Developer: **BBombs**
Server Count: **{len(ctx.app.cache.get_guilds_view())}**
Uptime: **{tdelta_str[0]} hours, {tdelta_str[1]} minutes**
Invite: [Click here]({INVITE_LINK_TEMPLATE.format(me.id)})
Source: [Click here]({GITHUB_LINK})""",
            colour=DEFAULT_EMBED_COLOUR,
        )
        .add_field(
            name="Latency",
            value=f"Gateway: {gateway_latency}\nREST: {(end - start) / 1000000:,.0f}ms",
        )
        .add_field(
            name="CPU Use",
            value=f"{round(psutil.cpu_percent(interval=None))}%",
            inline=True,
        )
        .add_field(
            name="Memory Use",
            value=f"{round(process.memory_info().vms / 1048576)}MB",
            inline=True,
        ),
    )


def load(bot: BattleFrontBot) -> None:
    bot.add_plugin(misc)


def unload(bot: BattleFrontBot) -> None:
    bot.remove_plugin(misc)


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
