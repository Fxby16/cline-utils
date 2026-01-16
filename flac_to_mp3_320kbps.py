import argparse
import os
import ffmpeg

def ffmpeg_convert(flac_file, mp3_file):
    try:
        (
        ffmpeg
        .input(flac_file)
        .output(
            mp3_file, 
            audio_bitrate='320k',
            map=['0:a', '0:v'],
            map_metadata=0,
            **{'c:v': 'copy', 'disposition:v': 'attached_pic'}
        )
        .overwrite_output()
        .run(quiet=True)
        )
    except ffmpeg.Error as e:
        print(f"Error converting {flac_file} to {mp3_file}: {e.stderr.decode()}")

    print(f"Successfully converted {flac_file} to {mp3_file}")

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

                print(f"Converting {flac_path} to {mp3_path}")
                ffmpeg_convert(flac_path, mp3_path)

def main():
    parser = argparse.ArgumentParser(description="Convert FLAC files to MP3.")
    parser.add_argument("input_dir", help="Directory containing FLAC files")
    parser.add_argument("output_dir", help="Directory to save MP3 files")
    args = parser.parse_args()

    convert(args.input_dir, args.output_dir)

if __name__ == "__main__":
    main()
