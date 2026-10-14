"""iPad landscape: WDA source frames come back in the portrait frame while /window/size is landscape."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_controller import FakeWDA, node
from wda_controller import PhoneController

# iPad Pro 13" (M5) as reported: landscape viewport 1376x1032, portrait frames 1032x1376.
PORTRAIT = {"width": 1032, "height": 1376}
LANDSCAPE = {"width": 1376, "height": 1032}


class OrientedWDA(FakeWDA):
    def __init__(self, orientation, size, root):
        super().__init__()
        self.orientation = orientation
        self.size = dict(size)
        self.source_root = dict(root)
        self.nodes = [
            node("Home screen icons", y=0, kind="Other", x=0, width=1032, height=1376),
            # Dock: at the landscape bottom; in the portrait frame (LANDSCAPE left) it sits at x 8-115.
            node("Dock", y=300, kind="Other", x=8, width=107, height=776),
            node("Safari", y=40, kind="Icon", x=20, width=80, height=90),
        ]

    def session(self, method, path, payload=None, timeout=None):
        if path == "/orientation":
            self.calls.append((method, path, payload))
            return self.orientation
        return super().session(method, path, payload, timeout)


def rects(controller):
    nodes, viewport = controller.tree(include_invisible=True)
    return {n["label"]: n["rect"] for n in nodes}, viewport


class LandscapeRectTests(unittest.TestCase):
    def make(self, orientation, size=LANDSCAPE, root=PORTRAIT):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        wda = OrientedWDA(orientation, size, root)
        return wda, PhoneController(wda, self.tmp.name)

    def assert_inside(self, rect, viewport):
        self.assertGreaterEqual(rect["x"], 0)
        self.assertGreaterEqual(rect["y"], 0)
        self.assertLessEqual(rect["x"] + rect["width"], viewport["width"])
        self.assertLessEqual(rect["y"] + rect["height"], viewport["height"])

    def test_landscape_left(self):
        _, controller = self.make("LANDSCAPE")
        found, viewport = rects(controller)
        self.assertEqual(viewport["units"], "device points")
        self.assertEqual(found["Home screen icons"], {"x": 0, "y": 0, "width": 1376, "height": 1032})
        dock = found["Dock"]
        self.assertEqual(dock, {"x": 300, "y": 1032 - 115, "width": 776, "height": 107})
        self.assertGreater(dock["y"], viewport["height"] / 2)  # the Dock is at the bottom
        for rect in found.values():
            self.assert_inside(rect, viewport)

    def test_landscape_right(self):
        _, controller = self.make("UIA_DEVICE_ORIENTATION_LANDSCAPERIGHT")
        found, viewport = rects(controller)
        self.assertEqual(found["Home screen icons"], {"x": 0, "y": 0, "width": 1376, "height": 1032})
        self.assertEqual(found["Dock"], {"x": 1376 - 1076, "y": 8, "width": 776, "height": 107})
        for rect in found.values():
            self.assert_inside(rect, viewport)

    def test_rotations_are_inverse_mirrors(self):
        _, left = self.make("LANDSCAPE")
        _, right = self.make("UIA_DEVICE_ORIENTATION_LANDSCAPERIGHT")
        a, _ = rects(left)
        b, _ = rects(right)
        r1, r2 = a["Safari"], b["Safari"]
        # A 180 degree turn between the two landscapes maps one rect onto the other.
        self.assertEqual(r1["x"], 1376 - r2["x"] - r2["width"])
        self.assertEqual(r1["y"], 1032 - r2["y"] - r2["height"])

    def test_element_rect_and_tap_centre_use_landscape_space(self):
        wda, controller = self.make("LANDSCAPE")
        rects(controller)
        wda.elements[0]["rect"] = {"x": 8, "y": 300, "width": 107, "height": 776}
        element = {"element_id": "target", "index": 0}
        rect = controller.element_rect(element)
        self.assertEqual(rect, {"x": 300, "y": 917, "width": 776, "height": 107})
        self.assertEqual(controller.element_rect(element), rect)  # not rotated twice
        tap = controller.describe(element)["tap"]
        self.assertEqual(tap, [688, 970])

    def test_portrait_is_noop(self):
        wda, controller = self.make("PORTRAIT", size=PORTRAIT, root=PORTRAIT)
        found, _ = rects(controller)
        self.assertEqual(found["Dock"], {"x": 8, "y": 300, "width": 107, "height": 776})
        self.assertNotIn(("GET", "/orientation", None), wda.calls)

    def test_matching_landscape_frames_are_noop(self):
        wda, controller = self.make("LANDSCAPE", size=LANDSCAPE, root=LANDSCAPE)
        found, _ = rects(controller)
        self.assertEqual(found["Dock"], {"x": 8, "y": 300, "width": 107, "height": 776})
        self.assertNotIn(("GET", "/orientation", None), wda.calls)


if __name__ == "__main__":
    unittest.main()
