"""links.py: đoạn nối công tắc -> cầu / điểm dịch chuyển."""

import unittest
from pathlib import Path

from App.Components.level_loader import load_levels
from App.Game.links import link_segments

ROOT = Path(__file__).resolve().parent.parent
CUSTOM = {lv.name: lv for lv in load_levels(ROOT / "levels", "custom")}
CLASSIC = {lv.name: lv for lv in load_levels(ROOT / "levels" / "classic", "classic")}


class LinkSegments(unittest.TestCase):
    def test_plain_levels_have_no_links(self):
        self.assertEqual(link_segments(CUSTOM["First Roll"]), [])

    def test_soft_switch_points_at_the_middle_of_its_bridge(self):
        segs = link_segments(CUSTOM["Soft Touch"])
        self.assertEqual(len(segs), 1)
        s = segs[0]
        self.assertEqual(s.source, (0, 6))
        self.assertEqual(s.target, (2.5, 8.5))  # nhóm cầu (2,7),(2,8),(2,9)
        self.assertEqual(s.kind, "toggle")
        self.assertEqual(s.group, 0)

    def test_permanent_modes_become_open_or_close(self):
        kinds = {s.kind for s in link_segments(CUSTOM["Two Keys"])}
        self.assertEqual(kinds, {"open"})
        kinds = {s.kind for s in link_segments(CUSTOM["Toggle Trap"])}
        self.assertEqual(kinds, {"toggle"})

    def test_one_segment_per_bridge_group_not_per_tile(self):
        # Switchboard: 6 công tắc, mỗi công tắc điều khiển 2 nhóm cầu (mỗi nhóm 3 ô)
        segs = link_segments(CUSTOM["Switchboard"])
        self.assertEqual(len(segs), 12)

    def test_split_switch_links_to_both_landing_cells(self):
        segs = [s for s in link_segments(CUSTOM["Split and Merge"]) if s.kind == "split"]
        self.assertEqual({s.target for s in segs}, {(1.5, 2.5), (3.5, 2.5)})
        self.assertTrue(all(s.group == -1 for s in segs))

    def test_mixed_effect_switch_gets_a_segment_per_group_with_its_own_kind(self):
        # Classic 23: công tắc (1,13) mở nhóm 3 và đảo nhóm 5
        segs = [s for s in link_segments(CLASSIC["Classic 23"]) if s.source == (1, 13)]
        by_group = {s.group: s.kind for s in segs}
        self.assertEqual(by_group, {3: "open", 5: "toggle"})

    def test_every_classic_level_computes(self):
        for lv in CLASSIC.values():
            with self.subTest(stage=lv.name):
                for s in link_segments(lv):
                    self.assertIn(s.kind, {"toggle", "open", "close", "split"})


if __name__ == "__main__":
    unittest.main()
