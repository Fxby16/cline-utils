import argparse
import subprocess
import os

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
            return sample_rate
    except (subprocess.CalledProcessError, OSError):
        pass
    return None

def run_subprocess(cmd, source, target):
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print(f"Successfully converted {source} to {target}")
    except subprocess.CalledProcessError as e:
        print(f"Error converting {source}:\n{e.stderr.decode()}")
        if os.path.exists(target):
            os.remove(target)

def ffmpeg_convert_mp3(source, target, bitrate, normalize_volume):
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
        cmd += ["-af", "loudnorm=I=-16:LRA=11:TP=-1.5"]
        if sample_rate:
            cmd += ["-ar", sample_rate]

    cmd += [
        "-c:v", "mjpeg",
        "-disposition:v", "attached_pic",
        "-map_metadata", "0",
        "-write_id3v2", "1",
        target
    ]

    run_subprocess(cmd, source, target)

def ffmpeg_convert_aac(source, target, bitrate, normalize_volume):
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
        cmd += ["-af", "loudnorm=I=-16:LRA=11:TP=-1.5"]
        if sample_rate:
            cmd += ["-ar", sample_rate]

    cmd += [
        "-c:v", "mjpeg",
        "-disposition:v", "attached_pic",
        "-map_metadata", "0",
        target
    ]

    run_subprocess(cmd, source, target)

def convert_file(source, target, codec, bitrate, normalize_volume, overwrite):
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
                return

    print(f"Converting {source} to {target}")
    try:
        if codec == "mp3":
            ffmpeg_convert_mp3(source, target, bitrate, normalize_volume)
        elif codec == "aac":
            ffmpeg_convert_aac(source, target, bitrate, normalize_volume)
    except KeyboardInterrupt:
        print(f"\nInterrupted! Deleting incomplete file {target}")
        if os.path.exists(target):
            os.remove(target)
        raise

def convert_dir(input_dir, output_dir, codec, bitrate, normalize_volume, overwrite):
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
            if file.lower().endswith('.flac'):
                flac_path = os.path.join(root, file)
                relative_path = os.path.relpath(root, input_dir)
                target_dir = os.path.join(output_dir, relative_path)
                
                if not os.path.exists(target_dir):
                    os.makedirs(target_dir)

                target_file = os.path.splitext(file)[0] + extension
                target_path = os.path.join(target_dir, target_file)

                convert_file(flac_path, target_path, codec, bitrate, normalize_volume, overwrite)

def convert(source, target, codec, bitrate, normalize_volume, overwrite):
    if os.path.isdir(source):
        convert_dir(source, target, codec, bitrate, normalize_volume, overwrite)
    elif os.path.isfile(source):
        convert_file(source, target, codec, bitrate, normalize_volume, overwrite)

def main():
    parser = argparse.ArgumentParser(description="Convert FLAC files to a lossy codec.")
    parser.add_argument("input", help="File or directory containing FLAC files")
    parser.add_argument("output", help="Output file or directory")
    parser.add_argument("codec", choices=["mp3", "aac"], help="Target codec")
    parser.add_argument("bitrate", help="Target bitrate (e.g. 192k, 320k)")
    parser.add_argument("--normalize_volume", action="store_true", help="Apply loudness normalization to output files")
    parser.add_argument("--overwrite", action="store_true", help="Force the script to overwrite the destination")
    args = parser.parse_args()

    convert(args.input, args.output, args.codec, args.bitrate, args.normalize_volume, args.overwrite)

if __name__ == "__main__":
    main()
