"""Projection contract: preserve legacy pixels, isolate red evidence, reject typos."""
import tempfile
import unittest
from pathlib import Path
import cv2
import numpy as np
import wm_tpl


class TemplateProjectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def image(self, name, pixels):
        path = Path(self.directory.name) / (name + '.png')
        ok, encoded = cv2.imencode('.png', pixels)
        self.assertTrue(ok)
        encoded.tofile(path)
        return str(path)

    def test_default_gray_is_pixel_identical_to_legacy_formula(self):
        pixels = np.random.default_rng(31).integers(0, 256, (80, 90, 3), dtype=np.uint8)
        path = self.image('legacy', pixels)
        gray = cv2.cvtColor(pixels, cv2.COLOR_BGR2GRAY).astype(np.float32)
        expected = gray - cv2.GaussianBlur(gray, (0, 0), 25)
        np.testing.assert_array_equal(wm_tpl.resid(path), expected)
        np.testing.assert_array_equal(wm_tpl.resid(path, projection='gray'), expected)
        tpl = expected[25:42, 30:58]
        self.assertEqual(wm_tpl.scan(path, tpl), wm_tpl.scan(path, tpl, projection='gray'))

    def test_red_excess_float_formula_and_location_across_backgrounds(self):
        rng = np.random.default_rng(47)
        glyph = rng.integers(0, 100, (18, 37), dtype=np.uint8)
        source = np.full((220, 240, 3), 30, dtype=np.uint8)
        target = np.full((260, 280, 3), 100, dtype=np.uint8)
        source[100:118, 90:127, 2] += glyph
        target[143:161, 170:207, 2] += glyph
        source_path = self.image('source', source)
        target_path = self.image('target', target)
        # Explicit float casting catches unsigned subtraction wraparound.
        mixed = np.array([[[200, 180, 10], [20, 30, 120], [90, 70, 80]]], dtype=np.uint8)
        mixed_path = self.image('mixed', mixed)
        excess = np.array([[0., 90., 0.]], dtype=np.float32)
        expected = excess - cv2.GaussianBlur(excess, (0, 0), 25)
        np.testing.assert_array_equal(wm_tpl.resid(mixed_path, projection='red_excess'), expected)
        tpl = wm_tpl.resid(source_path, projection='red_excess')[96:122, 86:131]
        found = wm_tpl.scan(target_path, tpl, return_location=True, projection='red_excess')
        self.assertEqual(found['source_coordinates'], [166, 139, 211, 165])
        self.assertGreater(found['ncc'], .99)
        self.assertEqual(found['ncc'], wm_tpl.scan(target_path, tpl, projection='red_excess'))

    def test_unknown_projection_rejected_by_both_entry_points(self):
        path = self.image('valid', np.zeros((30, 40, 3), dtype=np.uint8))
        with self.assertRaises(ValueError):
            wm_tpl.resid(path, projection='red_typo')
        with self.assertRaises(ValueError):
            wm_tpl.scan(path, np.ones((5, 7), dtype=np.float32), projection='red_typo')


if __name__ == '__main__':
    unittest.main()
