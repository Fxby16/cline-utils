#!/usr/bin/env python3
"""Extract a clip from a media file WITHOUT re-encoding (lossless stream copy).

This script cuts a segment using ffmpeg "stream copy" ("-c copy"), preserving the
original codecs/bitstream.

Notes / limitations:
- With stream copy, cutting is typically keyframe-aligned (start may snap to the
  nearest previous keyframe). For frame-accurate cuts you generally must re-encode.
- Some containers/codecs combinations may not support all stream types when copying.

Usage:
  extract_clip_lossless.py <input-file> -s <start> (-e <end> | -d <duration>) [-o <output-file>]

Examples:
  python extract_clip_lossless.py movie.mkv -s 00:10:00 -d 00:00:30
  python extract_clip_lossless.py movie.mp4 -s 600 -e 630 -o clip.mp4
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def _parse_time_to_seconds(value: str) -> float:
    """Parse ffmpeg-style time to seconds.

    Accepts:
    - seconds as int/float ("600", "12.5")
    - HH:MM:SS[.ms] ("01:02:03", "1:02:03.500")
    - MM:SS[.ms] ("10:30")
    """
    s = value.strip()
    try:
        return float(s)
    except ValueError:
        pass

    parts = s.split(":")
    if len(parts) not in (2, 3):
        raise ValueError(f"Invalid time format: {value!r}")

    try:
        if len(parts) == 2:
            minutes = int(parts[0])
            seconds = float(parts[1])
            return minutes * 60 + seconds

        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds
    except ValueError as exc:
        raise ValueError(f"Invalid time format: {value!r}") from exc


def _format_seconds_as_time(seconds: float) -> str:
    # Keep it simple; ffmpeg accepts plain seconds too, but HH:MM:SS is readable.
    if seconds < 0:
        seconds = 0
    total = int(seconds)
    hh = total // 3600
    mm = (total % 3600) // 60
    ss = total % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}"


def _which_or_die(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        print(f"{tool} not found in PATH", file=sys.stderr)
        raise SystemExit(2)
    return path


def _default_output_path(input_path: Path, start: str, end: str | None, duration: str | None) -> Path:
    # Keep same container by default.
    # Sanitize time strings for filenames.
    def sanitize(s: str) -> str:
        return (
            s.strip()
            .replace(":", "-")
            .replace(" ", "")
            .replace("/", "-")
            .replace("\\", "-")
        )

    start_s = sanitize(start)
    if duration:
        len_s = sanitize(duration)
        tag = f"{start_s}_d{len_s}"
    else:
        end_s = sanitize(end or "")
        tag = f"{start_s}_to_{end_s}"

    suffix = input_path.suffix or ".mkv"
    return input_path.with_name(f"{input_path.stem}_clip_{tag}{suffix}")


def build_ffmpeg_command(
    *,
    ffmpeg: str,
    input_file: str,
    start: str,
    end: str | None,
    duration: str | None,
    output_file: str,
    fast_seek: bool,
    map_all_streams: bool,
    audio_index: int | None,
    audio_lang: str | None,
    reset_timestamps: bool,
) -> list[str]:
    cmd: list[str] = [ffmpeg, "-hide_banner"]

    # Fast seek places -ss before -i (more efficient, but keyframe-aligned).
    if fast_seek:
        cmd += ["-ss", start]

    # Helps when timestamps are missing/odd; can reduce timestamp-related issues on copy.
    cmd += ["-fflags", "+genpts"]

    cmd += ["-i", input_file]

    # Accurate seek puts -ss after -i (still not truly frame-accurate with -c copy,
    # but can be closer in some cases).
    if not fast_seek:
        cmd += ["-ss", start]

    if duration:
        cmd += ["-t", duration]
    elif end:
        # Use -t with a computed duration to avoid ambiguous -to semantics.
        # This also guarantees the clip length is (end-start) regardless of seek mode.
        clip_len = _parse_time_to_seconds(end) - _parse_time_to_seconds(start)
        if clip_len <= 0:
            raise ValueError("End time must be greater than start time.")
        cmd += ["-t", _format_seconds_as_time(clip_len)]

    if map_all_streams:
        cmd += ["-map", "0"]
    elif audio_index is not None or audio_lang is not None:
        # Manual mapping: keep the first video stream and a chosen audio stream.
        # This is useful when --main-only would otherwise pick an undesired default audio.
        cmd += ["-map", "0:v:0"]
        if audio_index is not None:
            cmd += ["-map", f"0:a:{audio_index}"]
        else:
            # Map the first audio stream matching the language tag.
            # Example: -map 0:a:m:language:ita
            cmd += ["-map", f"0:a:m:language:{audio_lang}"]

    # Stream copy: keep original codecs (lossless extraction).
    cmd += ["-c", "copy"]

    # Reset stream timestamps so the clip starts from 0 for each stream.
    # This improves compatibility and often avoids non-monotonic DTS warnings.
    if reset_timestamps:
        cmd += ["-reset_timestamps", "1"]

    # Keep timestamps reasonably sane for clipped output.
    cmd += ["-avoid_negative_ts", "make_zero"]

    # Overwrite without prompting.
    cmd += ["-y", output_file]

    return cmd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract a clip without re-encoding (lossless stream copy).")
    parser.add_argument("input", help="Input media file")
    parser.add_argument("-s", "--start", required=True, help="Start time (e.g. 00:01:23.000 or seconds)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-e", "--end", help="End time (e.g. 00:01:53.000)")
    group.add_argument("-d", "--duration", help="Duration (e.g. 00:00:30.000)")
    parser.add_argument("-o", "--output", help="Output file path. Default: <input>_clip_<...>.<same_ext>")
    parser.add_argument(
        "--fast-seek",
        action="store_true",
        help="Place -ss before -i for faster seeking (usually keyframe-aligned). Default behavior.",
    )
    parser.add_argument(
        "--accurate-seek",
        action="store_true",
        help="Place -ss after -i (slower; can be closer, but still not frame-accurate with -c copy).",
    )
    parser.add_argument(
        "--map-all",
        action="store_true",
        help="Copy all streams from the input via -map 0 (this is the default).",
    )
    parser.add_argument(
        "--main-only",
        action="store_true",
        help="Only keep ffmpeg's default selected streams (usually 1 video + 1 audio).",
    )
    parser.add_argument(
        "--audio-index",
        type=int,
        help=(
            "When using --main-only, force a specific audio track by 0-based index (ffmpeg: 0:a:<index>). "
            "Example: --audio-index 1"
        ),
    )
    parser.add_argument(
        "--audio-lang",
        help=(
            "When using --main-only, force the audio track by language tag (ffmpeg: 0:a:m:language:<tag>). "
            "Example: --audio-lang ita"
        ),
    )
    parser.add_argument(
        "--keep-timestamps",
        action="store_true",
        help="Do not reset timestamps (disables -reset_timestamps 1).",
    )

    args = parser.parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 2

    output_path = Path(args.output) if args.output else _default_output_path(input_path, args.start, args.end, args.duration)

    ffmpeg = _which_or_die("ffmpeg")

    if args.fast_seek and args.accurate_seek:
        print("Choose only one of --fast-seek or --accurate-seek.", file=sys.stderr)
        return 2

    if args.audio_index is not None and args.audio_index < 0:
        print("--audio-index must be >= 0.", file=sys.stderr)
        return 2

    if args.audio_index is not None and args.audio_lang:
        print("Choose only one of --audio-index or --audio-lang.", file=sys.stderr)
        return 2

    # For stream copy, fast seek is typically what you want; keep it as default.
    fast_seek = True if not args.accurate_seek else False

    # Default to copying ALL streams (video, all audio tracks, subtitles, etc.).
    # Without -map 0 ffmpeg typically keeps only the "best" video/audio.
    map_all_streams = True if not args.main_only else False
    if args.map_all:
        map_all_streams = True

    if map_all_streams and (args.audio_index is not None or args.audio_lang):
        print("--audio-index/--audio-lang cannot be used with --map-all (it would still keep all audio tracks).", file=sys.stderr)
        return 2

    cmd = build_ffmpeg_command(
        ffmpeg=ffmpeg,
        input_file=str(input_path),
        start=args.start,
        end=args.end,
        duration=args.duration,
        output_file=str(output_path),
        fast_seek=fast_seek,
        map_all_streams=map_all_streams,
        audio_index=args.audio_index,
        audio_lang=args.audio_lang,
        reset_timestamps=not args.keep_timestamps,
    )

    print("Command:")
    print(" ".join(cmd))

    proc = subprocess.run(cmd)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
