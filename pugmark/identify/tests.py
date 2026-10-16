import shutil
import tempfile
from pathlib import Path

import cv2
import numpy as np
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from identify.coats import render_coat
from identify.engine import analyze

ROOT = Path(__file__).resolve().parents[1]


def _jpeg(image: np.ndarray, name: str) -> SimpleUploadedFile:
    ok, encoded = cv2.imencode(".jpg", image)
    assert ok
    return SimpleUploadedFile(name, encoded.tobytes(), content_type="image/jpeg")


class EngineTests(SimpleTestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))

    def test_same_coat_under_a_new_photo(self):
        morning = self.tmp / "morning.jpg"
        later = self.tmp / "later.jpg"
        cv2.imwrite(str(morning), render_coat(1, bg_seed=10))
        cv2.imwrite(str(later), render_coat(1, bg_seed=99, angle=7, bright=25, shift=(30, -20), scale=0.92))
        result = analyze(
            [
                {"id": "a", "name": "morning.jpg", "path": morning, "kind": "image"},
                {"id": "b", "name": "later.jpg", "path": later, "kind": "image"},
            ],
            self.tmp / "out-same",
            "/media/",
        )
        self.assertEqual(result["summary"]["verdict"], "same")
        self.assertEqual(result["summary"]["individuals"], 1)
        self.assertGreaterEqual(result["pairs"][0]["inliers"], 16)

    def test_different_coats(self):
        first = self.tmp / "a.jpg"
        second = self.tmp / "b.jpg"
        cv2.imwrite(str(first), render_coat(1, bg_seed=10))
        cv2.imwrite(str(second), render_coat(7, bg_seed=11))
        result = analyze(
            [
                {"id": "a", "name": "a.jpg", "path": first, "kind": "image"},
                {"id": "b", "name": "b.jpg", "path": second, "kind": "image"},
            ],
            self.tmp / "out-diff",
            "/media/",
        )
        self.assertEqual(result["summary"]["verdict"], "different")
        self.assertEqual(len(result["individuals"]), 2)
        self.assertLessEqual(result["pairs"][0]["inliers"], 9)

    def test_bundled_different_sample_is_repeatable(self):
        first = ROOT / "static" / "samples" / "coat-a-morning.jpg"
        second = ROOT / "static" / "samples" / "coat-b.jpg"
        verdicts = []
        for index in range(2):
            result = analyze(
                [
                    {"id": "a", "name": first.name, "path": first, "kind": "image"},
                    {"id": "b", "name": second.name, "path": second, "kind": "image"},
                ],
                self.tmp / f"demo-different-{index}",
                "/media/",
            )
            verdicts.append(result["pairs"][0]["verdict"])
        self.assertEqual(verdicts, ["different", "different"])

    def test_mixed_set_clusters_the_repeat_only(self):
        specs = {
            "a": render_coat(1, bg_seed=10),
            "a2": render_coat(1, bg_seed=40, angle=-6, bright=-12, shift=(-20, 16)),
            "b": render_coat(9, bg_seed=12),
        }
        items = []
        for key, image in specs.items():
            path = self.tmp / f"{key}.jpg"
            cv2.imwrite(str(path), image)
            items.append({"id": key, "name": path.name, "path": path, "kind": "image"})
        result = analyze(items, self.tmp / "out-mix", "/media/")
        self.assertEqual(result["summary"]["verdict"], "mixed")
        self.assertEqual(result["summary"]["individuals"], 2)
        self.assertIn("review", result["summary"]["dek"].lower())
        sizes = sorted(len(group["file_ids"]) for group in result["individuals"])
        self.assertEqual(sizes, [1, 2])

    def test_real_photographs_of_different_species_do_not_match(self):
        hero = ROOT / "static" / "img" / "hero.jpg"
        flank = ROOT / "static" / "img" / "flank.jpg"
        result = analyze(
            [
                {"id": "tiger", "name": "hero.jpg", "path": hero, "kind": "image"},
                {"id": "leo", "name": "flank.jpg", "path": flank, "kind": "image"},
            ],
            self.tmp / "out-wild",
            "/media/",
        )
        self.assertEqual(result["pairs"][0]["verdict"], "different")

    def test_video_of_the_same_coat_matches_the_still(self):
        still = self.tmp / "still.jpg"
        clip = self.tmp / "clip.mp4"
        cv2.imwrite(str(still), render_coat(3, bg_seed=4))
        writer = cv2.VideoWriter(str(clip), cv2.VideoWriter_fourcc(*"mp4v"), 8, (980, 760))
        self.assertTrue(writer.isOpened())
        for shift in (0, 8, -6):
            writer.write(render_coat(3, bg_seed=6, bright=10, shift=(shift, 0)))
        writer.release()
        result = analyze(
            [
                {"id": "still", "name": "still.jpg", "path": still, "kind": "image"},
                {"id": "clip", "name": "clip.mp4", "path": clip, "kind": "video"},
            ],
            self.tmp / "out-video",
            "/media/",
        )
        self.assertEqual(result["summary"]["verdict"], "same")


class UploadTests(TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.override = override_settings(MEDIA_ROOT=self.tmp)
        self.override.enable()
        self.addCleanup(self.override.disable)

    def test_upload_same_coat_renders_report(self):
        response = self.client.post(
            reverse("create_scan"),
            {
                "files": [
                    _jpeg(render_coat(1, 10), "morning.jpg"),
                    _jpeg(render_coat(1, 99, angle=7, bright=18, shift=(24, -10)), "later.jpg"),
                ]
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Same animal")
        self.assertContains(response, "morning.jpg")

    def test_one_file_is_rejected(self):
        response = self.client.post(
            reverse("create_scan"),
            {"files": [_jpeg(render_coat(1, 10), "only.jpg")]},
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "at least two", status_code=400)
