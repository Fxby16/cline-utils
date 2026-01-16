# Convert FLAC files to MP3 at 320kbps using ffmpeg, preserving metadata and album art.
# Usage: python flac_to_mp3_320kbps.py <input-directory> <output-directory>

import argparse
import subprocess
import os

def ffmpeg_convert(flac_file, mp3_file):
    cmd = [
        "ffmpeg", "-y",
        "-i", flac_file,
        "-map", "0:a",
        "-map", "0:v?",
        "-c:a", "libmp3lame",
        "-b:a", "320k",
        "-c:v", "mjpeg",
        "-disposition:v", "attached_pic",
        "-map_metadata", "0",
        "-write_id3v2", "1",
        mp3_file
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        print(f"Successfully converted {flac_file} to {mp3_file}")
    except subprocess.CalledProcessError as e:
        print(f"Error converting {flac_file}:\n{e.stderr.decode()}")
        if os.path.exists(mp3_file):
            os.remove(mp3_file)


def convert(input_dir, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    for root, _, files in os.walk(input_dir):
        for file in files:
            if file.lower().endswith('.flac'):
                flac_path = os.path.join(root, file)
                relative_path = os.path.relpath(root, input_dir)
                mp3_dir = os.path.join(output_dir, relative_path)
                
                if not os.path.exists(mp3_dir):
                    os.makedirs(mp3_dir)

                mp3_file = os.path.splitext(file)[0] + '.mp3'
                mp3_path = os.path.join(mp3_dir, mp3_file)

                if os.path.exists(mp3_path):
                    print(f"Skipping {flac_path} (already converted)")
                    continue

                print(f"Converting {flac_path} to {mp3_path}")
                try:
                    ffmpeg_convert(flac_path, mp3_path)
                except KeyboardInterrupt:
                    print(f"\nInterrupted! Deleting incomplete file {mp3_path}")
                    if os.path.exists(mp3_path):
                        os.remove(mp3_path)
                    raise

def main():
    parser = argparse.ArgumentParser(description="Convert FLAC files to MP3.")
    parser.add_argument("input_dir", help="Directory containing FLAC files")
    parser.add_argument("output_dir", help="Directory to save MP3 files")
    args = parser.parse_args()

    convert(args.input_dir, args.output_dir)

if __name__ == "__main__":
    main()
