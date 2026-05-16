import shutil
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from scripts import media_ocr, ocr_media


class OcrMediaTests(unittest.TestCase):
    def test_make_ocr_config_preserves_video_frames(self):
        args = Namespace(
            model="vision-model",
            stt_model="stt-model",
            language="en",
            video_frames=7,
            prompt="extract text",
            full_video=True,
        )
        vision_client = object()
        stt_client = object()

        cfg = ocr_media._make_ocr_config(args, vision_client, stt_client)

        self.assertIs(cfg.client, vision_client)
        self.assertIs(cfg.stt_client, stt_client)
        self.assertEqual(cfg.model, "vision-model")
        self.assertEqual(cfg.stt_model, "stt-model")
        self.assertEqual(cfg.language, "en")
        self.assertEqual(cfg.video_frames, 7)
        self.assertEqual(cfg.prompt, "extract text")
        self.assertTrue(cfg.full_video)

    def test_parser_uses_thumbnail_video_by_default_and_full_video_opt_in(self):
        parser = ocr_media.build_parser()

        default_args = parser.parse_args(["--input", "scan.jsonl"])
        full_args = parser.parse_args(["--input", "scan.jsonl", "--full-video"])

        self.assertFalse(default_args.full_video)
        self.assertTrue(full_args.full_video)

    def test_parser_defaults_to_current_xai_image_model(self):
        parser = ocr_media.build_parser()

        args = parser.parse_args(["--input", "scan.jsonl"])

        self.assertEqual(args.model, "grok-4.3")

    def test_ocr_video_cleans_temporary_frame_directory(self):
        class FakeTemporaryDirectory:
            def __init__(self, path: Path):
                self.path = path
                self.entered = False
                self.exited = False

            def __enter__(self):
                self.entered = True
                self.path.mkdir(parents=True, exist_ok=True)
                return str(self.path)

            def __exit__(self, exc_type, exc, tb):
                self.exited = True
                shutil.rmtree(self.path, ignore_errors=True)

        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="visible text")
                )
            ]
        )
        client = MagicMock()
        client.chat.completions.create.return_value = response

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video_path = root / "video.mp4"
            frame_dir = root / "frames"
            video_path.write_bytes(b"fake-video")
            tempdir = FakeTemporaryDirectory(frame_dir)

            def fake_run(args, **kwargs):
                if args[0] == "ffprobe":
                    return SimpleNamespace(stdout="2.0")
                if args[0] == "ffmpeg":
                    Path(args[-1]).write_bytes(b"fake-jpeg")
                    return SimpleNamespace(stdout="")
                raise AssertionError(f"unexpected subprocess: {args}")

            with patch.object(media_ocr.tempfile, "TemporaryDirectory", return_value=tempdir):
                with patch.object(media_ocr.subprocess, "run", side_effect=fake_run):
                    text = media_ocr.ocr_video(
                        client, "vision-model", video_path, video_frames=1
                    )

        self.assertEqual(text, "visible text")
        self.assertTrue(tempdir.entered)
        self.assertTrue(tempdir.exited)
        self.assertFalse(frame_dir.exists())


if __name__ == "__main__":
    unittest.main()
