from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.media_store import get_browser_preview_path


class MediaStoreTests(unittest.TestCase):
    @patch("src.media_store.subprocess.run")
    def test_aiff_uses_cached_wav_preview(self, mock_run) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "meeting.aiff"
            preview = Path(temp_dir) / "meeting.preview.wav"
            source.write_bytes(b"FORM")

            def create_preview(command, **_kwargs) -> None:
                Path(command[-1]).write_bytes(b"RIFF")

            mock_run.side_effect = create_preview
            result = get_browser_preview_path(source)

            self.assertEqual(result, preview)
            self.assertEqual(mock_run.call_args.args[0][:5], ["afconvert", "-f", "WAVE", "-d", "LEI16"])

    def test_wav_is_served_without_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "meeting.wav"
            source.write_bytes(b"RIFF")

            self.assertEqual(get_browser_preview_path(source), source)


if __name__ == "__main__":
    unittest.main()
