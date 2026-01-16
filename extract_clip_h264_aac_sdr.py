# Extract a video clip from a file using ffmpeg and reencode it in H.264/AAC, with HDR tonemapping if needed.
# Useful if you need to upload a short clip to a platform that doesn't support HDR or that does heavy compression on higher quality videos or that only supports mp4 files.
# Disclaimer: the tonemapping used here may not be suitable for all types of HDR content. Adjust the tonemapping parameters as needed for your specific use case.
# Usage: extract_clip.py <input-file> -s <start-time> (-e <end-time> | -d <duration>) [-o <output-file>]

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

VIDEO_ENCODING = "-c:v libx264 -preset veryfast -crf 18 -pix_fmt yuv420p"
AUDIO_ENCODING = "-c:a aac -b:a 192k"
HDR_TONEMAPPING2 = "zscale=t=linear:npl=100,zscale=transfer=linear:primaries=bt2020:matrix=bt2020nc, tonemap=mobius:param=0.5, zscale=transfer=bt709:primaries=bt709:matrix=bt709"
HDR_TONEMAPPING = "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=mobius:desat=2,zscale=t=bt709:m=bt709:r=tv,format=yuv420p"

def get_file_info(file_name):
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        print("ffprobe not found in PATH", file=sys.stderr)
        return 2

    cmd = [ffprobe, "-v", "error", "-show_format", "-show_streams", file_name]

    proc = subprocess.run(cmd, capture_output=True, text=True)

    return proc.stdout

def split_streams(file_info):
    streams = []
    stream_blocks = []

    for line in file_info.splitlines():
        if line.strip() == "[STREAM]":
            in_stream = True
            current_block = []
        elif line.strip() == "[/STREAM]":
            in_stream = False
            if current_block:
                stream_blocks.append(current_block)
        elif in_stream and "=" in line:
            current_block.append(line.strip())
    
    # Parse each stream block into a dictionary
    for block in stream_blocks:
        stream_info = {}
        for line in block:
            if "=" in line:
                key, value = line.split("=", 1)
                stream_info[key] = value
        streams.append(stream_info)

    return streams

def is_hdr(video_stream):
    if "bt2020" in video_stream["color_space"] and "bt2020" in video_stream["color_primaries"]:
        return True
    else:
        return False
    
def run_ffmpeg(filename, start_time, duration, end_time, is_hdr, output_file):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg not found in PATH", file=sys.stderr)
        return 2

    cmd = [ffmpeg]
    
    if start_time:
        cmd.extend(["-ss", start_time])
    
    cmd.extend(["-i", filename])
    
    if duration:
        cmd.extend(["-t", duration])
    elif end_time:
        cmd.extend(["-to", end_time])
    
    if is_hdr:
        cmd.extend(["-vf",HDR_TONEMAPPING])

    cmd.extend(VIDEO_ENCODING.split())
    cmd.extend(AUDIO_ENCODING.split())
    
    if output_file:
        cmd.append(output_file)
    else:
        cmd.append("output.mp4")

    print("Command:", cmd)
    
    proc = subprocess.run(cmd)
    
    return proc.returncode


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        print("Usage: extract_clip.py <input-file>", file=sys.stderr)
        return 2
    
    filename = argv[0]
    start_time = None
    end_time = None
    duration = None
    output_file = None
    
    i = 1  # Skip first argument (filename)
    while i < len(argv):
        if argv[i] in ['-s', '--start'] and i + 1 < len(argv):
            start_time = argv[i + 1]
            i += 2
        elif argv[i] in ['-e', '--end'] and i + 1 < len(argv):
            end_time = argv[i + 1]
            i += 2
        elif argv[i] in ['-d', '--duration'] and i + 1 < len(argv):
            duration = argv[i + 1]
            i += 2
        elif argv[i] in ['-o', '--output'] and i + 1 < len(argv):
            output_file = argv[i + 1]
            i += 2
        else:
            i += 1

    if start_time == None or (end_time == None and duration == None):
        print("You must specify a start time and either an end time or a duration.", file=sys.stderr)
        return 2

    file_info = get_file_info(argv[0])
    streams = split_streams(file_info)

    # Find video stream
    video_stream = None
    for stream in streams:
        if stream["codec_type"] == "video":
            video_stream = stream
            break

    hdr = is_hdr(video_stream)

    run_ffmpeg(filename, start_time, duration, end_time, hdr, output_file)
    

if __name__ == "__main__":
    main()
