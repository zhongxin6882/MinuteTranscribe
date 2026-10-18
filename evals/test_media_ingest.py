from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.media_ingest import _normalize_audio_to_wav, _should_normalize_audio_before_transcription


class MediaIngestTests(unittest.TestCase):
    def test_should_normalize_aiff_before_transcription(self) -> None:
        self.assertTrue(_should_normalize_audio_before_transcription(Path("demo.aiff")))
        self.assertTrue(_should_normalize_audio_before_transcription(Path("demo.aif")))
        self.assertFalse(_should_normalize_audio_before_transcription(Path("demo.wav")))

    @patch("src.media_ingest.subprocess.run")
    def test_normalize_audio_to_wav_uses_afconvert(self, mock_run) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "meeting.aiff"
            source.write_bytes(b"FORM")
            output = _normalize_audio_to_wav(source, Path(temp_dir))

        self.assertEqual(output.suffix, ".wav")
        mock_run.assert_called_once()
        command = mock_run.call_args.args[0]
        self.assertEqual(command[:5], ["afconvert", "-f", "WAVE", "-d", "LEI16"])
        self.assertEqual(command[5], str(source))


if __name__ == "__main__":
    unittest.main()
