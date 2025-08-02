import logging
import os
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def generate_game_banner(team_names: list[str], score: tuple[int, int], winning_players: list[str]) -> BytesIO:
    """Generate a game summary banner by formating the winner template with the provided values.

    Should be run in a separate task.

    Parameters
    ----------
    team_names : list[str]
        The name for the two participating teams.
    score : tuple[int]
        The final game scores.
    winning_players : list[str]
        A list of display names for players on the winning team.

    Returns
    -------
    BytesIO
        The created jpeg image as bytes.

    """
    src_dir = str(Path(os.path.abspath(__file__)).parents[1])
    buffer = BytesIO()

    try:
        img = Image.open(os.path.join(src_dir, "static", "img", "banner_template.jpg"))
    except FileNotFoundError:
        logger.error("Game banner template image 'src/static/img/banner_template.jpg' not found")
        return buffer

    w, h = 1745, 769  # Image width, height
    template = ImageDraw.Draw(img)

    # Title text
    mussels = ImageFont.truetype(os.path.join(src_dir, "static", "font", "mussels_black.ttf"), 80)
    title1_colour = (0, 29, 48)
    title1_length = template.textlength(team_names[0].upper(), mussels)
    title1_position = ((w / 2 - title1_length) - 40, h / 2)

    title2_colour = (44, 0, 0)
    title2_length = template.textlength(team_names[1].upper(), mussels)
    title2_position = ((w / 2 + title2_length) + 40, h / 2)

    # Subtitle text
    helvetica = ImageFont.truetype(os.path.join(src_dir, "static", "font", "helvetika_bold.ttf"), 30)
    subtitle_colour = (255, 255, 255)
    subtitle_position = (w / 2, h / 2 + 250)
    players_str = "\n".join(player for player in winning_players)

    # Score text
    eras = ImageFont.truetype(os.path.join(src_dir, "static", "font", "eras_itc_bold.ttf"), 48)
    score_colour = (255, 255, 255)
    score_position = (w / 2, h / 2 - 225)
    score_str = f"{score[0]}  -  {score[1]}"

    # Emoji text
    emoji = ImageFont.truetype(os.path.join(src_dir, "static", "font", "emoji.ttf"), 60)
    l_emoji_position = (w / 2 - 450, h / 2 - 165)
    r_emoji_position = (w / 2 + 450, h / 2 - 165)
    l_emoji = "👑" if score[0] > score[1] else "💔"
    r_emoji = "👑" if score[0] < score[1] else "💔"

    if score[0] == score[1]:
        l_emoji = "🟰"
        r_emoji = "🟰"

    template.text(title1_position, team_names[0].upper(), font=mussels, fill=title1_colour, anchor="lm")
    template.text(title2_position, team_names[1].upper(), font=mussels, fill=title2_colour, anchor="rm")
    template.multiline_text(
        subtitle_position, players_str, font=helvetica, fill=subtitle_colour, anchor="mm", align="center", spacing=10
    )
    template.text(score_position, score_str, font=eras, fill=score_colour, anchor="mm")
    template.text(l_emoji_position, l_emoji, font=emoji, fill=title1_colour, anchor="lm")
    template.text(r_emoji_position, r_emoji, font=emoji, fill=title2_colour, anchor="rm")

    img.save(buffer, format="jpeg")
    return buffer


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
