#!/usr/bin/env python3
"""Build reproducible Edge TTS voice auditions from episode storyboards."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional


def run(command: list[str], attempts: int = 3) -> None:
    last_error: Optional[subprocess.CalledProcessError] = None
    for attempt in range(1, attempts + 1):
        try:
            subprocess.run(command, check=True)
            return
        except subprocess.CalledProcessError as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(attempt)
    assert last_error is not None
    raise last_error


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return float(result.stdout.strip())


def synthesize(
    text: str,
    output: Path,
    subtitles: Path,
    voice: str,
    rate: str,
    pitch: str,
    volume: str,
) -> None:
    run(
        [
            sys.executable,
            "-m",
            "edge_tts",
            "--voice",
            voice,
            f"--rate={rate}",
            f"--pitch={pitch}",
            f"--volume={volume}",
            "--text",
            text,
            "--write-media",
            str(output),
            "--write-subtitles",
            str(subtitles),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.jobs <= 8:
        parser.error("--jobs must stay within 1..8")

    spec_path = args.spec.resolve()
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)

    jobs: list[dict] = []
    for episode in spec["episodes"]:
        storyboard_path = Path(episode["storyboard"]).resolve()
        storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
        scenes = storyboard["scenes"]
        if len(scenes) < 2:
            raise ValueError(f"{episode['id']}: at least two scenes are required")
        sample_text = "\n".join(
            [
                str(scenes[0]["narration"]).strip(),
                str(scenes[-2]["narration"]).strip(),
            ]
        )
        for candidate in episode["candidates"]:
            stem = f"{episode['id']}__{candidate['id']}"
            jobs.append(
                {
                    "episode": episode,
                    "candidate": candidate,
                    "storyboard": storyboard_path,
                    "sample_text": sample_text,
                    "media": output / f"{stem}.mp3",
                    "vtt": output / f"{stem}.vtt",
                }
            )

    with ThreadPoolExecutor(max_workers=min(args.jobs, len(jobs))) as executor:
        futures = {
            executor.submit(
                synthesize,
                job["sample_text"],
                job["media"],
                job["vtt"],
                job["candidate"]["voice"],
                job["candidate"].get("rate", "-15%"),
                job["candidate"].get("pitch", "-1Hz"),
                job["candidate"].get("volume", "+0%"),
            ): job
            for job in jobs
        }
        for future in as_completed(futures):
            future.result()

    rows = []
    for job in jobs:
        candidate = job["candidate"]
        rows.append(
            {
                "episode_id": job["episode"]["id"],
                "title": job["episode"]["title"],
                "relationship": job["episode"]["relationship"],
                "recommended_candidate": job["episode"]["recommended_candidate"],
                "candidate_id": candidate["id"],
                "voice": candidate["voice"],
                "rate": candidate.get("rate", "-15%"),
                "pitch": candidate.get("pitch", "-1Hz"),
                "volume": candidate.get("volume", "+0%"),
                "sample_text": job["sample_text"],
                "media": str(job["media"]),
                "media_sha256": sha256(job["media"]),
                "duration_sec": round(duration(job["media"]), 3),
                "vtt": str(job["vtt"]),
                "vtt_sha256": sha256(job["vtt"]),
            }
        )
    manifest = {
        "schema": "edge-tts-voice-auditions/v1",
        "spec": str(spec_path),
        "normal_speed_playback_required": True,
        "items": rows,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "PASS", "samples": len(rows)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
