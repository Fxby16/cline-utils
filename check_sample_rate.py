import argparse
import os
import subprocess
from pathlib import Path


def get_sample_rate(file_path: Path):
    """Return sample rate from first audio stream, or None if unavailable."""
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
        str(file_path),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise RuntimeError(
            "ffprobe non trovato. Installa FFmpeg e assicurati che ffprobe sia nel PATH."
        )

    if result.returncode != 0:
        return None

    output = result.stdout.strip()
    if not output:
        return None

    try:
        return int(output)
    except ValueError:
        return None


def iter_files(directory: Path, recursive: bool):
    if recursive:
        for root, _, files in os.walk(directory):
            for name in files:
                yield Path(root) / name
    else:
        for entry in directory.iterdir():
            if entry.is_file():
                yield entry


def ask_yes_no(prompt: str) -> bool:
    answer = input(prompt).strip().lower()
    return answer in ("y", "yes", "s", "si")


def main():
    parser = argparse.ArgumentParser(
        description="Lista (ed eventualmente elimina) file con sample rate audio sopra una soglia."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory da analizzare (default: corrente).",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=48000,
        help="Soglia sample rate in Hz (default: 48000).",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Analizza anche le sottocartelle.",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Elimina i file che superano la soglia.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Con --delete, elimina senza chiedere conferma.",
    )

    args = parser.parse_args()
    directory = Path(args.directory).resolve()

    if not directory.exists() or not directory.is_dir():
        print(f"Directory non valida: {directory}")
        return 1

    flagged = []
    scanned = 0

    try:
        for file_path in iter_files(directory, args.recursive):
            scanned += 1
            sr = get_sample_rate(file_path)
            if sr is None:
                continue
            if sr > args.threshold:
                flagged.append((file_path, sr))
    except RuntimeError as err:
        print(str(err))
        return 2

    if not flagged:
        print(f"Nessun file con sample rate > {args.threshold} Hz.")
        print(f"File scansionati: {scanned}")
        return 0

    print(f"File con sample rate > {args.threshold} Hz:")
    for file_path, sr in flagged:
        print(f"- {file_path}  ({sr} Hz)")

    if args.delete:
        deleted = 0
        for file_path, sr in flagged:
            should_delete = args.force or ask_yes_no(
                f"Eliminare {file_path} ({sr} Hz)? [y/N]: "
            )
            if should_delete:
                try:
                    file_path.unlink()
                    deleted += 1
                    print(f"Eliminato: {file_path}")
                except OSError as err:
                    print(f"Errore eliminando {file_path}: {err}")
        print(f"Totale eliminati: {deleted}/{len(flagged)}")

    print(f"File scansionati: {scanned}")
    print(f"File sopra soglia: {len(flagged)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
