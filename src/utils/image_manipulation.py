import os
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def generate_game_banner(team_names: list[str], score: tuple[int], winning_players: list[str]) -> BytesIO:
    """Generate a game summary banner by formating the winner template with the provided values.

    Should be run in a separate thread to prevent blocking.

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

    w, h = 1745, 769  # Image width, height
    img = Image.open(os.path.join(src_dir, "static", "img", "winner_template.jpg"))
    template = ImageDraw.Draw(img)

    # Title text
    mussels = ImageFont.truetype(os.path.join(src_dir, "static", "font", "mussels_black.ttf"), 100)
    title1_colour = (0, 34, 56)
    title1_length = template.textlength(team_names[0], mussels)
    title1_position = ((w / 2 - title1_length) - 50, h / 2)

    title2_colour = (54, 0, 0)
    title2_length = template.textlength(team_names[1], mussels)
    title2_position = ((w / 2 + title2_length) + 50, h / 2)

    # Subtitle text
    helvetica = ImageFont.truetype(os.path.join(src_dir, "static", "font", "helvetika_bold.ttf"), 36)
    subtitle_colour = (255, 255, 255)
    subtitle_position = (w / 2, h / 2 + 150)
    players_str = ", ".join(player for player in winning_players)

    # Score text
    eras = ImageFont.truetype(os.path.join(src_dir, "static", "font", "eras_itc_bold.ttf"), 48)
    score_colour = (0, 0, 0)
    score_position = (w / 2, h / 2 - 225)
    score_str = f"{score[0]}  -  {score[1]}"

    # Emoji text
    emoji = ImageFont.truetype(os.path.join(src_dir, "static", "font", "emoji.ttf"), 48)
    r_emoji_position = (title1_position[0] + title1_length / 2, h / 2 - 165)
    l_emoji_position = (title2_position[0] - title2_length / 2, h / 2 - 165)
    r_emoji = "👑" if score[0] > score[1] else "💔"
    l_emoji = "👑" if score[0] < score[1] else "💔"

    template.text(title1_position, team_names[0], font=mussels, fill=title1_colour, anchor="lm")
    template.text(title2_position, team_names[1], font=mussels, fill=title2_colour, anchor="rm")
    template.text(subtitle_position, players_str, font=helvetica, fill=score_colour, anchor="mm")
    template.text(score_position, score_str, font=eras, fill=subtitle_colour, anchor="mm")
    template.text(r_emoji_position, r_emoji, font=emoji, fill=title1_colour, anchor="lm")
    template.text(l_emoji_position, l_emoji, font=emoji, fill=title2_colour, anchor="rm")

    b = BytesIO()
    img.save(b, format="jpeg")
    return b


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
