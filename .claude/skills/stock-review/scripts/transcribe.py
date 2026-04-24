#!/usr/bin/env python3
"""Three-tier subtitle extraction: L1 embedded -> L2 OCR -> L3 ASR."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def probe_video(video_path: Path) -> dict:
    """Return {duration, has_audio, embedded_subs: [lang, ...]}."""
    cmd = ["ffprobe", "-v", "error", "-print_format", "json",
           "-show_streams", "-show_format", str(video_path)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {r.stderr}")
    data = json.loads(r.stdout)
    duration = float(data.get("format", {}).get("duration", 0))
    streams = data.get("streams", [])
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    embedded_subs = [
        s.get("tags", {}).get("language", "und")
        for s in streams if s.get("codec_type") == "subtitle"
    ]
    return {"duration": duration, "has_audio": has_audio,
            "embedded_subs": embedded_subs}


def extract_embedded(video_path: Path, out_srt: Path, sub_index: int = 0) -> Path:
    out_srt.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-i", str(video_path),
           "-map", f"0:s:{sub_index}", str(out_srt)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg subtitle extract failed: {r.stderr[:500]}")
    return out_srt


def try_ocr(video_path: Path, out_srt: Path) -> Path | None:
    """Stub: 占位 OCR 实现；未启用时直接返回 None。
    后续集成 RapidOCR 时替换此函数。"""
    return None


def run_asr(video_path: Path, out_srt: Path, hotwords_path: Path | None) -> Path:
    """Invoke FunASR paraformer-zh via CLI wrapper.

    Prerequisite: `pip install funasr modelscope` and model weights cached.
    """
    out_srt.parent.mkdir(parents=True, exist_ok=True)
    wav_path = out_srt.with_suffix(".wav")
    # 抽 16k mono wav
    r = subprocess.run(
        ["ffmpeg", "-y", "-i", str(video_path),
         "-ar", "16000", "-ac", "1", "-vn", str(wav_path)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extract failed: {r.stderr[:500]}")

    hotwords: list[str] = []
    if hotwords_path and hotwords_path.exists():
        hotwords = [line.strip() for line in hotwords_path.read_text().splitlines()
                    if line.strip() and not line.startswith("#")]

    # 使用 funasr python API
    try:
        from funasr import AutoModel
    except ImportError as e:
        raise RuntimeError("FunASR not installed; pip install funasr modelscope") from e

    model = AutoModel(model="paraformer-zh", vad_model="fsmn-vad",
                      punc_model="ct-punc")
    res = model.generate(input=str(wav_path),
                         hotword=" ".join(hotwords) if hotwords else None)
    # res: list[{"key": ..., "text": ..., "sentence_info": [{"start","end","text"}, ...]}]
    _write_srt(res, out_srt)
    wav_path.unlink(missing_ok=True)
    return out_srt


def _write_srt(asr_result: list[dict], out_srt: Path) -> None:
    def fmt_ts(ms: float) -> str:
        ms = int(ms)
        s, ms = divmod(ms, 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines: list[str] = []
    idx = 1
    for item in asr_result:
        for seg in item.get("sentence_info") or []:
            start = seg.get("start", 0)
            end = seg.get("end", start + 1000)
            text = seg.get("text", "").strip()
            if not text:
                continue
            lines.append(f"{idx}\n{fmt_ts(start)} --> {fmt_ts(end)}\n{text}\n")
            idx += 1
    out_srt.write_text("\n".join(lines), encoding="utf-8")


def srt_to_txt(srt_path: Path) -> Path:
    import pysrt
    txt_path = srt_path.with_suffix(".txt")
    subs = pysrt.open(str(srt_path), encoding="utf-8")
    text = "\n".join(s.text.strip() for s in subs if s.text.strip())
    txt_path.write_text(text, encoding="utf-8")
    return txt_path


def run(*, video_path: Path, out_dir: Path, hotwords_path: Path | None,
        enable_ocr: bool = False) -> dict:
    info = probe_video(video_path)
    if info["duration"] < 60:
        return {"skipped": "too_short"}
    if not info["has_audio"] and not info["embedded_subs"]:
        return {"skipped": "no_audio"}

    out_dir.mkdir(parents=True, exist_ok=True)
    # 用文件 sha1 前 12 位作 stem，避免同名冲突
    stem = hashlib.sha1(str(video_path).encode()).hexdigest()[:12]
    srt_out = out_dir / f"{stem}.srt"

    method: str
    if info["embedded_subs"]:
        srt = extract_embedded(video_path, srt_out)
        method = "L1"
    elif enable_ocr:
        srt = try_ocr(video_path, srt_out)
        if srt:
            method = "L2"
        else:
            srt = run_asr(video_path, srt_out, hotwords_path)
            method = "L3"
    else:
        srt = run_asr(video_path, srt_out, hotwords_path)
        method = "L3"

    txt = srt_to_txt(srt)
    return {"method": method, "srt_path": str(srt), "txt_path": str(txt),
            "duration_sec": info["duration"]}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("video", type=Path)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--hotwords", type=Path, default=None)
    p.add_argument("--enable-ocr", action="store_true")
    args = p.parse_args(argv)

    result = run(video_path=args.video, out_dir=args.out_dir,
                 hotwords_path=args.hotwords, enable_ocr=args.enable_ocr)
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())