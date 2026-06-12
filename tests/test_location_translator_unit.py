"""The offset -> LSP UTF-16 direction of the Location Translator.

Fast pure coverage for the reverse translation the Rewrite made
load-bearing (PRD 0002 "Reverse translation"): Match Sites report Ranges
back to the agent, so a wrong UTF-16 count here misplaces every audit.
"""

from __future__ import annotations

from ropey.location_translator import offset_to_position, position_to_offset
from ropey.model import Position

SNAKE = "\U0001f40d"  # astral: 1 code point, 2 UTF-16 units


class TestOffsetToPosition:
    def test_ascii_offsets_map_one_to_one(self):
        assert offset_to_position("value = 1\n", 6) == Position(0, 6)

    def test_lines_are_zero_based_and_newline_aware(self):
        text = "first = 1\nsecond = 2\n"
        assert offset_to_position(text, 10) == Position(1, 0)
        assert offset_to_position(text, 17) == Position(1, 7)

    def test_an_astral_character_counts_two_utf16_units(self):
        text = f'x = "{SNAKE}"; y = 2\n'
        # Code-point offset of 'y': x(1) space(1) =(1) space(1) "(1)
        # snake(1) "(1) ;(1) space(1) = 9; UTF-16 character: snake is 2.
        assert offset_to_position(text, 9) == Position(0, 10)

    def test_bmp_cjk_characters_count_one_utf16_unit(self):
        text = '名前 = "x"\n'
        assert offset_to_position(text, 3) == Position(0, 3)

    def test_offsets_clamp_to_the_text_bounds(self):
        assert offset_to_position("ab\n", -3) == Position(0, 0)
        assert offset_to_position("ab\n", 99) == Position(1, 0)

    def test_round_trips_with_the_forward_translation(self):
        text = f'banner = "{SNAKE}{SNAKE}"; 値 = conf.get_attribute("名前")\n'
        for offset in range(len(text)):
            position = offset_to_position(text, offset)
            assert position_to_offset(text, position) == offset
