"""iPad landscape: WDA source frames come back in the portrait frame while /window/size is landscape.

The fake follows WDA 16.14.0: GET /orientation answers "LANDSCAPE" for both landscapes
(_wdOrientationsMapping), and GET /rotation answers z=270 or z=90 (fb_rotationMapping).
"""
from pathlib import Path
import sys
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_controller import FakeWDA, node
from wda_client import WDAError
from wda_controller import ROTATION_UNKNOWN_WARNING, PhoneController

# iPad Pro 13" (M5) as reported: landscape viewport 1376x1032, portrait frames 1032x1376.
PORTRAIT = {"width": 1032, "height": 1376}
LANDSCAPE = {"width": 1376, "height": 1032}
LEFT, RIGHT = {"x": 0, "y": 0, "z": 270}, {"x": 0, "y": 0, "z": 90}


def dock(at_right=False):
    # Dock: at the landscape bottom; in the portrait frame it is a tall strip at one edge (x 8-115 reported).
    return node("Dock", y=300, kind="Other", x=1032 - 115 if at_right else 8, width=107, height=776)


class OrientedWDA(FakeWDA):
    def __init__(self, rotation, size=LANDSCAPE, root=PORTRAIT):
        super().__init__()
        self.rotation = rotation
        self.size = dict(size)
        self.source_root = dict(root)
        self.nodes = [node("Home screen icons", y=0, kind="Other", x=0, width=1032, height=1376),
                      dock(), node("Safari", y=40, kind="Icon", x=20, width=80, height=90)]
        # Portrait-frame element: centre (62, 1250).
        self.elements[0]["rect"] = {"x": 12, "y": 1228, "width": 100, "height": 44}

    def session(self, method, path, payload=None, timeout=None):
        if path == "/orientation":
            self.calls.append((method, path, payload))
            return "PORTRAIT" if self.size["width"] < self.size["height"] else "LANDSCAPE"
        if path == "/rotation":
            self.calls.append((method, path, payload))
            if isinstance(self.rotation, Exception):
                raise self.rotation
            return self.rotation
        return super().session(method, path, payload, timeout)

    def source(self):
        # A real source root names the foreground app, like activeAppInfo.
        self.source_root["bundleId"] = self.app
        return super().source()


def rects(controller):
    nodes, viewport = controller.tree(include_invisible=True)
    return {n["label"]: n["rect"] for n in nodes}, viewport


class LandscapeRectTests(unittest.TestCase):
    def make(self, rotation, **kwargs):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        wda = OrientedWDA(rotation, **kwargs)
        return wda, PhoneController(wda, tmp.name)

    def assert_inside(self, rect, viewport):
        self.assertGreaterEqual(rect["x"], 0)
        self.assertGreaterEqual(rect["y"], 0)
        self.assertLessEqual(rect["x"] + rect["width"], viewport["width"])
        self.assertLessEqual(rect["y"] + rect["height"], viewport["height"])

    def test_orientation_cannot_tell_landscapes_apart(self):
        wda, _ = self.make(RIGHT)
        self.assertEqual(wda.session("GET", "/orientation"), "LANDSCAPE")

    def test_rotation_270_maps_left(self):
        wda, controller = self.make(LEFT)
        found, viewport = rects(controller)
        self.assertEqual(viewport["units"], "device points")
        self.assertEqual(found["Home screen icons"], {"x": 0, "y": 0, "width": 1376, "height": 1032})
        self.assertEqual(found["Dock"], {"x": 300, "y": 1032 - 115, "width": 776, "height": 107})
        for rect in found.values():
            self.assert_inside(rect, viewport)
        self.assertNotIn(("GET", "/orientation", None), wda.calls)

    def test_rotation_90_maps_right(self):
        wda, controller = self.make(RIGHT)
        wda.nodes[1] = dock(at_right=True)
        found, viewport = rects(controller)
        self.assertEqual(found["Home screen icons"], {"x": 0, "y": 0, "width": 1376, "height": 1032})
        self.assertEqual(found["Dock"], {"x": 1376 - 1076, "y": 1032 - 115, "width": 776, "height": 107})
        for rect in found.values():
            self.assert_inside(rect, viewport)

    def test_rotations_are_180_degree_mirrors(self):
        _, left = self.make(LEFT)
        _, right = self.make(RIGHT)
        r1, r2 = rects(left)[0]["Safari"], rects(right)[0]["Safari"]
        self.assertEqual(r1["x"], 1376 - r2["x"] - r2["width"])
        self.assertEqual(r1["y"], 1032 - r2["y"] - r2["height"])

    def test_unknown_rotation_uses_dock_geometry(self):
        for rotation in (None, {"x": -1, "y": -1, "z": -1}, WDAError("unknown command", "no /rotation")):
            with self.subTest(rotation=rotation):
                wda, controller = self.make(rotation)
                wda.nodes[1] = dock(at_right=True)
                self.assertEqual(rects(controller)[0]["Dock"]["y"], 1032 - 115)  # right mapping
                wda2, controller2 = self.make(rotation)
                self.assertEqual(rects(controller2)[0]["Dock"]["y"], 1032 - 115)  # left mapping
                self.assertFalse(controller.rotation_unknown)

    def test_unknown_rotation_without_geometry_skips_and_warns(self):
        wda, controller = self.make(None)
        wda.nodes = [node("Safari", y=40, kind="Icon", x=20, width=80, height=90)]
        found, _ = rects(controller)
        self.assertEqual(found["Safari"], {"x": 20, "y": 40, "width": 80, "height": 90})
        self.assertTrue(controller.rotation_unknown)
        result = controller.observe()
        self.assertIn(ROTATION_UNKNOWN_WARNING, result["warnings"])
        self.assertTrue(ROTATION_UNKNOWN_WARNING.startswith("rotation_unknown"))

    def test_selector_tap_without_prior_tree_read(self):
        wda, controller = self.make(LEFT)
        found = controller.find({"label": "Target"})
        self.assertFalse(any(call[1].startswith("/source") for call in wda.calls[:1]))
        self.assertEqual(found["elements"][0]["tap"], [1250, 970])
        wda2, controller2 = self.make(LEFT)
        result = controller2.tap(selector={"label": "Target"})
        self.assertTrue(result["action_executed"])
        self.assertIn(("GET", "/rotation", None), wda2.calls)  # detected at use time, before the click
        self.assertLess(next(i for i, c in enumerate(wda2.calls) if c[1] == "/rotation"),
                        next(i for i, c in enumerate(wda2.calls) if c[1].endswith("/click")))

    def test_element_rect_is_converted_once(self):
        _, controller = self.make(LEFT)
        element = {"element_id": "target", "index": 0}
        first = controller.element_rect(element)
        self.assertEqual(controller.element_rect(element), first)
        self.assertEqual(first, {"x": 1228, "y": 920, "width": 44, "height": 100})

    def test_landscape_tree_then_rotate_to_portrait(self):
        wda, controller = self.make(LEFT)
        rects(controller)
        self.assertEqual(controller.describe({"element_id": "target", "index": 0})["tap"], [1250, 970])
        wda.size, wda.source_root = dict(PORTRAIT), dict(PORTRAIT)
        wda.elements[0]["rect"] = {"x": 12, "y": 666, "width": 100, "height": 44}
        with unittest.mock.patch("wda_controller.time.monotonic", return_value=10**9):
            described = controller.describe({"element_id": "target", "index": 0})
        self.assertEqual(described["tap"], [62, 688])

    def test_landscape_tree_then_portrait_find_is_unrotated(self):
        wda, controller = self.make(LEFT)
        rects(controller)
        wda.size, wda.source_root = dict(PORTRAIT), dict(PORTRAIT)
        wda.elements[0]["rect"] = {"x": 12, "y": 666, "width": 100, "height": 44}
        with unittest.mock.patch("wda_controller.time.monotonic", return_value=10**9):
            found = controller.find({"label": "Target"})
        element = found["elements"][0]
        self.assertEqual(element["rect"], [12, 666, 100, 44])
        self.assertEqual(element["tap"], [62, 688])
        self.assertIn((1376, 1032, "com.example.phone"), controller._frames)  # keyed by viewport size and app

    def expire_viewport(self, controller):
        stamp, viewport = controller._viewport_cache
        controller._viewport_cache = (stamp - 10, viewport)

    def test_landscape_flip_without_tree_read(self):
        wda, controller = self.make(LEFT)
        rects(controller)
        self.assertEqual(controller.describe({"element_id": "target", "index": 0})["tap"], [1250, 970])
        wda.rotation = RIGHT  # 180 degree flip: same viewport size
        self.expire_viewport(controller)
        source_reads = sum(1 for call in wda.calls if call[1].startswith("/source"))
        self.assertEqual(controller.describe({"element_id": "target", "index": 0})["tap"], [126, 62])
        self.assertEqual(sum(1 for call in wda.calls if call[1].startswith("/source")), source_reads)

    def test_flip_with_rotation_unavailable_uses_cached_geometry(self):
        wda, controller = self.make(LEFT)
        rects(controller)
        wda.rotation = None
        self.expire_viewport(controller)
        self.assertEqual(controller.describe({"element_id": "target", "index": 0})["tap"], [1250, 970])

    def test_unknown_side_is_asked_again_every_time(self):
        wda, controller = self.make(None)
        wda.nodes = [node("Safari", y=40, kind="Icon", x=20, width=80, height=90)]
        rects(controller)
        self.assertTrue(controller.rotation_unknown)
        before = sum(1 for call in wda.calls if call[1] == "/rotation")
        controller.describe({"element_id": "target", "index": 0})
        controller.describe({"element_id": "target", "index": 0})
        self.assertEqual(sum(1 for call in wda.calls if call[1] == "/rotation"), before + 2)
        wda.rotation = LEFT
        self.assertEqual(controller.describe({"element_id": "target", "index": 0})["tap"], [1250, 970])
        self.assertFalse(controller.rotation_unknown)

    def test_app_switch_rechecks_frame_shape(self):
        wda, controller = self.make(LEFT)
        rects(controller)
        # Another app whose frames already match the landscape viewport.
        wda.app, wda.source_root = "com.example.other", dict(LANDSCAPE)
        wda.elements[0]["rect"] = {"x": 100, "y": 100, "width": 100, "height": 44}
        self.expire_viewport(controller)
        self.assertEqual(controller.describe({"element_id": "target", "index": 0})["tap"], [150, 122])

    def test_tap_that_opens_another_app_rechecks_frames_within_ttl(self):
        wda, controller = self.make(LEFT)
        rects(controller)
        controller.tap(selector={"label": "Target"})  # this tap opens another app
        wda.app, wda.source_root = "com.example.other", dict(LANDSCAPE)
        wda.elements[0]["rect"] = {"x": 100, "y": 100, "width": 100, "height": 44}
        # No viewport expiry: the next selector use is well inside ROTATION_VIEWPORT_TTL.
        found = controller.find({"label": "Target"})
        self.assertEqual(found["elements"][0]["tap"], [150, 122])

    def test_failed_rotation_read_leaves_element_for_retry(self):
        wda, controller = self.make(LEFT)
        original = wda.source
        wda.source = lambda: (_ for _ in ()).throw(WDAError("timeout", "source read failed"))
        element = {"element_id": "target", "index": 0}
        with self.assertRaises(WDAError):
            controller.element_rect(element)
        self.assertFalse(element.get("_rotated"))
        wda.source = original
        self.assertEqual(controller.element_rect(element)["x"], 1228)

    def test_portrait_is_noop(self):
        wda, controller = self.make(LEFT, size=PORTRAIT, root=PORTRAIT)
        found, _ = rects(controller)
        self.assertEqual(found["Dock"], {"x": 8, "y": 300, "width": 107, "height": 776})
        self.assertEqual(controller.describe({"element_id": "target", "index": 0})["tap"], [62, 1250])
        self.assertNotIn(("GET", "/rotation", None), wda.calls)

    def test_matching_landscape_frames_are_noop(self):
        wda, controller = self.make(LEFT, size=LANDSCAPE, root=LANDSCAPE)
        found, _ = rects(controller)
        self.assertEqual(found["Dock"], {"x": 8, "y": 300, "width": 107, "height": 776})
        self.assertNotIn(("GET", "/rotation", None), wda.calls)

    def test_rotation_is_cached_per_viewport(self):
        wda, controller = self.make(LEFT)
        for _ in range(3):
            controller.describe({"element_id": "target", "index": 0})
        self.assertEqual(sum(1 for call in wda.calls if call[1] == "/rotation"), 1)
        self.assertEqual(sum(1 for call in wda.calls if call[1].startswith("/source")), 1)



if __name__ == "__main__":
    unittest.main()
