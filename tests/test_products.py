"""Checks for the pure functions: python -m unittest discover tests"""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import usgs_products as U
from engine import energy_megatons, rupture_length_km, depth_class, mmi_info


class Rake(unittest.TestCase):
    def test_styles(self):
        self.assertEqual(U.classify_rake(0)[0], "Strike-Slip")
        self.assertEqual(U.classify_rake(180)[0], "Strike-Slip")
        self.assertEqual(U.classify_rake(-155), ("Strike-Slip", "Right-lateral"))
        self.assertEqual(U.classify_rake(-17), ("Strike-Slip", "Left-lateral"))
        self.assertEqual(U.classify_rake(90)[0], "Reverse / Thrust")
        self.assertEqual(U.classify_rake(-90)[0], "Normal")
        self.assertEqual(U.classify_rake(140)[0], "Oblique Reverse")   # was mislabelled Oblique Normal
        self.assertEqual(U.classify_rake(-140)[0], "Oblique Normal")
        self.assertEqual(U.classify_rake(None), (None, None))


class Engine(unittest.TestCase):
    def test_depth(self):
        self.assertTrue(depth_class(13).startswith("Shallow"))
        self.assertTrue(depth_class(175).startswith("Intermediate"))
        self.assertTrue(depth_class(400).startswith("Deep"))

    def test_energy_and_length(self):
        self.assertAlmostEqual(energy_megatons(7.7), 5.4, delta=0.2)
        self.assertAlmostEqual(rupture_length_km(7.7), 10 ** (-2.44 + 0.59 * 7.7), delta=0.1)

    def test_mmi(self):
        self.assertEqual(mmi_info(9.0)["roman"], "IX")
        self.assertIsNone(mmi_info(0))


if __name__ == "__main__":
    unittest.main()
