import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

SCRIPT = Path(__file__).parent.parent / ".claude/skills/stock-review/scripts/transcribe.py"
spec = importlib.util.spec_from_file_location("transcribe", SCRIPT)
transcribe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(transcribe)


class TestRouting:
    def test_too_short_returns_skip(self, tmp_path: Path):
        with patch.object(transcribe, "probe_video",
                          return_value={"duration": 30, "has_audio": True,
                                         "embedded_subs": []}):
            result = transcribe.run(video_path=tmp_path / "v.mp4",
                                     out_dir=tmp_path / "out",
                                     hotwords_path=None,
                                     enable_ocr=False)
        assert result == {"skipped": "too_short"}

    def test_no_audio_returns_skip(self, tmp_path: Path):
        with patch.object(transcribe, "probe_video",
                          return_value={"duration": 600, "has_audio": False,
                                         "embedded_subs": []}):
            result = transcribe.run(video_path=tmp_path / "v.mp4",
                                     out_dir=tmp_path / "out",
                                     hotwords_path=None,
                                     enable_ocr=False)
        assert result == {"skipped": "no_audio"}

    def test_embedded_subs_use_L1(self, tmp_path: Path):
        (tmp_path / "out").mkdir()
        with patch.object(transcribe, "probe_video",
                          return_value={"duration": 600, "has_audio": True,
                                         "embedded_subs": ["chi_sim"]}), \
             patch.object(transcribe, "extract_embedded",
                          return_value=tmp_path / "out" / "v.srt") as m1, \
             patch.object(transcribe, "srt_to_txt",
                          return_value=tmp_path / "out" / "v.txt"):
            result = transcribe.run(video_path=tmp_path / "v.mp4",
                                     out_dir=tmp_path / "out",
                                     hotwords_path=None,
                                     enable_ocr=False)
        assert result["method"] == "L1"
        assert m1.called

    def test_fallthrough_to_L3(self, tmp_path: Path):
        (tmp_path / "out").mkdir()
        with patch.object(transcribe, "probe_video",
                          return_value={"duration": 600, "has_audio": True,
                                         "embedded_subs": []}), \
             patch.object(transcribe, "run_asr",
                          return_value=tmp_path / "out" / "v.srt") as m3, \
             patch.object(transcribe, "srt_to_txt",
                          return_value=tmp_path / "out" / "v.txt"):
            result = transcribe.run(video_path=tmp_path / "v.mp4",
                                     out_dir=tmp_path / "out",
                                     hotwords_path=None,
                                     enable_ocr=False)
        assert result["method"] == "L3"
        assert m3.called

    def test_ocr_enabled_tries_L2_first(self, tmp_path: Path):
        (tmp_path / "out").mkdir()
        with patch.object(transcribe, "probe_video",
                          return_value={"duration": 600, "has_audio": True,
                                         "embedded_subs": []}), \
             patch.object(transcribe, "try_ocr",
                          return_value=tmp_path / "out" / "v.srt") as m2, \
             patch.object(transcribe, "srt_to_txt",
                          return_value=tmp_path / "out" / "v.txt"):
            result = transcribe.run(video_path=tmp_path / "v.mp4",
                                     out_dir=tmp_path / "out",
                                     hotwords_path=None,
                                     enable_ocr=True)
        assert result["method"] == "L2"
        assert m2.called

    def test_ocr_miss_falls_to_L3(self, tmp_path: Path):
        (tmp_path / "out").mkdir()
        with patch.object(transcribe, "probe_video",
                          return_value={"duration": 600, "has_audio": True,
                                         "embedded_subs": []}), \
             patch.object(transcribe, "try_ocr", return_value=None), \
             patch.object(transcribe, "run_asr",
                          return_value=tmp_path / "out" / "v.srt"), \
             patch.object(transcribe, "srt_to_txt",
                          return_value=tmp_path / "out" / "v.txt"):
            result = transcribe.run(video_path=tmp_path / "v.mp4",
                                     out_dir=tmp_path / "out",
                                     hotwords_path=None,
                                     enable_ocr=True)
        assert result["method"] == "L3"