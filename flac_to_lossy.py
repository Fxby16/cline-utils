import argparse
import subprocess
import os
import shutil
import json
import re
import time

LOUDNORM_BASE_FILTER = "loudnorm=I=-16:LRA=11:TP=-1.5"
PASSTHROUGH_LOSSY_CODECS = {"mp3", "aac"}

def get_source_sample_rate(source):
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=sample_rate",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        source,
    ]
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        sample_rate = result.stdout.strip()
        if sample_rate.isdigit():
            # Limit to 48 kHz for compatibility.
            return str(min(int(sample_rate), 48000))
        return "48000"
    except (subprocess.CalledProcessError, OSError):
        pass
    return None


def get_source_audio_codec(source):
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        source,
    ]
    try:
        result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        codec = result.stdout.strip().lower()
        return codec or None
    except (subprocess.CalledProcessError, OSError):
        return None

def run_subprocess(cmd, source, target):
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print(f"Successfully converted {source} to {target}")
        return True
    except subprocess.CalledProcessError as e:
        stderr_text = e.stderr.decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else str(e.stderr)
        print(f"Error converting {source}:\n{stderr_text}")
        if os.path.exists(target):
            os.remove(target)
        return False


def copy_file(source, target, overwrite):
    if os.path.exists(target):
        try:
            source_mtime = os.path.getmtime(source)
            target_mtime = os.path.getmtime(target)
        except OSError:
            source_mtime = None
            target_mtime = None

        if not overwrite:
            if source_mtime is not None and target_mtime is not None and source_mtime > target_mtime:
                print(f"Re-copying {source} (source is newer than existing file)")
            else:
                print(f"Skipping {source} (copy is up-to-date)")
                return False

    print(f"Copying {source} to {target}")
    try:
        shutil.copy2(source, target)
        print(f"Successfully copied {source} to {target}")
        return True
    except OSError as e:
        print(f"Error copying {source}:\n{e}")
        if os.path.exists(target):
            os.remove(target)
        return False


def get_two_pass_loudnorm_filter(source):
    base_filter = LOUDNORM_BASE_FILTER
    analysis_filter = f"{base_filter}:print_format=json"

    analysis_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-i",
        source,
        "-map",
        "0:a:0",
        "-af",
        analysis_filter,
        "-f",
        "null",
        os.devnull,
    ]

    try:
        result = subprocess.run(
            analysis_cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (subprocess.CalledProcessError, OSError) as e:
        error_output = e.stderr if isinstance(e, subprocess.CalledProcessError) else str(e)
        print(f"Warning: loudnorm analysis failed for {source}, falling back to single-pass.\n{error_output}")
        return base_filter

    match = re.search(r"\{\s*\"input_i\".*?\}", result.stderr, re.DOTALL)
    if not match:
        print(f"Warning: loudnorm analysis output not found for {source}, falling back to single-pass.")
        return base_filter

    try:
        stats = json.loads(match.group(0))
        return (
            f"{base_filter}"
            f":measured_I={stats['input_i']}"
            f":measured_LRA={stats['input_lra']}"
            f":measured_TP={stats['input_tp']}"
            f":measured_thresh={stats['input_thresh']}"
            f":offset={stats['target_offset']}"
            ":linear=true:print_format=summary"
        )
    except (KeyError, ValueError) as e:
        print(f"Warning: loudnorm analysis parse failed for {source}, falling back to single-pass.\n{e}")
        return base_filter


def get_normalization_filter(source, use_two_pass):
    if use_two_pass:
        return get_two_pass_loudnorm_filter(source)
    return LOUDNORM_BASE_FILTER


def ffmpeg_convert_mp3(source, target, bitrate, normalize_volume, use_two_pass):
    sample_rate = get_source_sample_rate(source)

    cmd = [
        "ffmpeg", "-y",
        "-i", source,
        "-map", "0:a",
        "-map", "0:v?",
        "-c:a", "libmp3lame",
        "-b:a", bitrate,
    ]

    if normalize_volume:
        cmd += ["-af", get_normalization_filter(source, use_two_pass)]
        if sample_rate:
            cmd += ["-ar", sample_rate]

    cmd += [
        "-c:v", "mjpeg",
        "-disposition:v", "attached_pic",
        "-map_metadata", "0",
        "-write_id3v2", "1",
        target
    ]

    return run_subprocess(cmd, source, target)

def ffmpeg_convert_aac(source, target, bitrate, normalize_volume, use_two_pass):
    sample_rate = get_source_sample_rate(source)

    cmd = [
        "ffmpeg", "-y",
        "-i", source,
        "-map", "0:a",
        "-map", "0:v?",
        "-c:a", "aac",
        "-b:a", bitrate,
    ]

    if normalize_volume:
        cmd += ["-af", get_normalization_filter(source, use_two_pass)]
        if sample_rate:
            cmd += ["-ar", sample_rate]

    cmd += [
        "-c:v", "mjpeg",
        "-disposition:v", "attached_pic",
        "-map_metadata", "0",
        target
    ]

    return run_subprocess(cmd, source, target)

def convert_file(source, target, codec, bitrate, normalize_volume, overwrite, use_two_pass):
    if os.path.exists(target):
        try:
            flac_mtime = os.path.getmtime(source)
            target_mtime = os.path.getmtime(target)
        except OSError:
            flac_mtime = None
            target_mtime = None

        if not overwrite:
            if flac_mtime is not None and target_mtime is not None and flac_mtime > target_mtime:
                print(f"Re-converting {source} (FLAC is newer than existing {codec.upper()} )")
            else:
                print(f"Skipping {source} ({codec.upper()} is up-to-date)")
                return False

    print(f"Converting {source} to {target}")
    try:
        if codec == "mp3":
            return ffmpeg_convert_mp3(source, target, bitrate, normalize_volume, use_two_pass)
        elif codec == "aac":
            return ffmpeg_convert_aac(source, target, bitrate, normalize_volume, use_two_pass)
        return False
    except KeyboardInterrupt:
        print(f"\nInterrupted! Deleting incomplete file {target}")
        if os.path.exists(target):
            os.remove(target)
        raise

def convert_dir(input_dir, output_dir, codec, bitrate, normalize_volume, overwrite, use_two_pass, stats):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    codec = codec.lower()
    extension = ""

    if codec == "mp3":
        extension = ".mp3"
    elif codec == "aac":
        extension = ".m4a"

    for root, _, files in os.walk(input_dir):
        for file in files:
            source_path = os.path.join(root, file)
            source_codec = get_source_audio_codec(source_path)

            if source_codec is None:
                continue

            relative_path = os.path.relpath(root, input_dir)
            target_dir = os.path.join(output_dir, relative_path)

            if not os.path.exists(target_dir):
                os.makedirs(target_dir)

            if source_codec in PASSTHROUGH_LOSSY_CODECS:
                target_path = os.path.join(target_dir, file)
                if copy_file(source_path, target_path, overwrite):
                    stats["copied"] += 1
            else:
                target_file = os.path.splitext(file)[0] + extension
                target_path = os.path.join(target_dir, target_file)
                if convert_file(source_path, target_path, codec, bitrate, normalize_volume, overwrite, use_two_pass):
                    stats["converted"] += 1
            

def convert(source, target, codec, bitrate, normalize_volume, overwrite, use_two_pass):
    stats = {"converted": 0, "copied": 0}

    if os.path.isdir(source):
        convert_dir(source, target, codec, bitrate, normalize_volume, overwrite, use_two_pass, stats)
    elif os.path.isfile(source):
        source_codec = get_source_audio_codec(source)
        if source_codec in PASSTHROUGH_LOSSY_CODECS:
            if copy_file(source, target, overwrite):
                stats["copied"] += 1
        else:
            if convert_file(source, target, codec, bitrate, normalize_volume, overwrite, use_two_pass):
                stats["converted"] += 1

    return stats


def format_elapsed_time(seconds):
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"

def main():
    parser = argparse.ArgumentParser(description="Convert FLAC files to a lossy codec.")
    parser.add_argument("input", help="File or directory containing FLAC files")
    parser.add_argument("output", help="Output file or directory")
    parser.add_argument("codec", choices=["mp3", "aac"], help="Target codec")
    parser.add_argument("bitrate", help="Target bitrate (e.g. 192k, 320k)")
    parser.add_argument("--normalize_volume", action="store_true", help="Apply loudness normalization to output files")
    parser.add_argument("--single_pass_normalize", action="store_true", help="Use single-pass loudnorm instead of two-pass (faster, less accurate)")
    parser.add_argument("--overwrite", action="store_true", help="Force the script to overwrite the destination")
    args = parser.parse_args()

    use_two_pass = not args.single_pass_normalize
    start_time = time.time()
    stats = convert(args.input, args.output, args.codec, args.bitrate, args.normalize_volume, args.overwrite, use_two_pass)
    elapsed = time.time() - start_time

    print("\n--- Conversion Summary ---")
    print(f"Time elapsed: {format_elapsed_time(elapsed)}")
    print(f"Files converted: {stats['converted']}")
    print(f"Files copied: {stats['copied']}")

if __name__ == "__main__":
    main()
