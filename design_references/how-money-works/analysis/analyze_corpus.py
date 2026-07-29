from __future__ import annotations

import html
import json
import re
import statistics
import subprocess
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
METADATA = ROOT / "metadata"
VIDEOS = ROOT / "videos"
FRAMES = ROOT / "frames"
CORPUS_PATH = ROOT / "corpus.json"
OUTPUT_JSON = ROOT / "analysis" / "corpus_metrics.json"
OUTPUT_MD = ROOT / "analysis" / "video_index.md"

TIMESTAMP_RE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2}\.\d{3}) --> "
    r"(?P<end>\d{2}:\d{2}:\d{2}\.\d{3})"
)
TAG_RE = re.compile(r"<[^>]+>")
WORD_RE = re.compile(r"\b[\w’'-]+\b", re.UNICODE)
SENTENCE_RE = re.compile(r"(?<=[.!?…])\s+")
SCENE_TIME_RE = re.compile(r"pts_time:(?P<time>\d+(?:\.\d+)?)")


def seconds(value: str) -> float:
    hours, minutes, rest = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(rest)


def parse_vtt(path: Path) -> list[dict[str, object]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    cues: list[dict[str, object]] = []
    index = 0
    while index < len(lines):
        match = TIMESTAMP_RE.match(lines[index].strip())
        if not match:
            index += 1
            continue
        start = seconds(match.group("start"))
        end = seconds(match.group("end"))
        index += 1
        text_lines: list[str] = []
        while index < len(lines) and lines[index].strip():
            text_lines.append(lines[index].strip())
            index += 1
        text = html.unescape(TAG_RE.sub("", " ".join(text_lines)))
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            cues.append({"start": start, "end": end, "text": text})
        index += 1
    return cues


def fmt_time(value: float) -> str:
    minutes, second = divmod(int(round(value)), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{second:02d}"
    return f"{minutes}:{second:02d}"


def scene_times(video: Path) -> list[float]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "info",
        "-i",
        str(video),
        "-vf",
        "select='gt(scene,0.30)',showinfo",
        "-an",
        "-f",
        "null",
        "-",
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    return [
        float(match.group("time"))
        for match in SCENE_TIME_RE.finditer(result.stderr)
    ]


def contact_sheets(video: Path, video_id: str) -> None:
    output_dir = FRAMES / video_id
    output_dir.mkdir(parents=True, exist_ok=True)
    if list(output_dir.glob("uniform-*.jpg")) and list(
        output_dir.glob("scene-*.jpg")
    ):
        return
    uniform = output_dir / "uniform-%03d.jpg"
    scene = output_dir / "scene-%03d.jpg"
    uniform_filter = (
        "fps=1/10,scale=384:216,"
        "tile=5x4:nb_frames=20:padding=2:margin=2"
    )
    scene_filter = (
        "select='gt(scene,0.30)',scale=384:216,"
        "tile=5x4:nb_frames=20:padding=2:margin=2"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-vf",
            uniform_filter,
            "-fps_mode",
            "vfr",
            str(uniform),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video),
            "-vf",
            scene_filter,
            "-fps_mode",
            "vfr",
            str(scene),
        ],
        check=True,
    )


def reconstructed_transcript(cues: list[dict[str, object]]) -> str:
    accumulated: list[str] = []
    for cue in cues:
        incoming = WORD_RE.findall(str(cue["text"]))
        if not incoming:
            continue
        overlap = 0
        maximum = min(len(accumulated), len(incoming))
        for size in range(maximum, 1, -1):
            if [
                word.casefold() for word in accumulated[-size:]
            ] == [word.casefold() for word in incoming[:size]]:
                overlap = size
                break
        accumulated.extend(incoming[overlap:])
    return " ".join(accumulated)


def transcript_metrics(cues: list[dict[str, object]], duration: float) -> dict[str, object]:
    raw_transcript = " ".join(str(cue["text"]) for cue in cues)
    raw_transcript = re.sub(r"\s+", " ", raw_transcript).strip()
    transcript = reconstructed_transcript(cues)
    words = WORD_RE.findall(transcript)
    sentences = [
        sentence.strip()
        for sentence in SENTENCE_RE.split(raw_transcript)
        if sentence.strip()
    ]
    sentence_words = [len(WORD_RE.findall(sentence)) for sentence in sentences]
    punctuation_events = len(re.findall(r"[.!?…]", raw_transcript))
    sentence_metrics_reliable = punctuation_events >= max(5, len(words) / 80)
    questions = raw_transcript.count("?")
    return {
        "transcript": transcript,
        "word_count": len(words),
        "words_per_minute": round(len(words) / max(duration / 60, 0.01), 1),
        "sentence_count": len(sentences),
        "sentence_metrics_reliable": sentence_metrics_reliable,
        "average_sentence_words": round(statistics.mean(sentence_words), 1)
        if sentence_words and sentence_metrics_reliable
        else 0,
        "median_sentence_words": statistics.median(sentence_words)
        if sentence_words and sentence_metrics_reliable
        else 0,
        "question_count": questions,
        "questions_per_1000_words": round(questions / max(len(words), 1) * 1000, 1),
        "first_90_seconds": " ".join(
            reconstructed_transcript(
                [cue for cue in cues if float(cue["start"]) < 90]
            ).split()
        ),
        "cues": cues,
    }


def main() -> None:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    results: list[dict[str, object]] = []
    for selected in corpus:
        video_id = selected["id"]
        info_path = METADATA / f"{video_id}.info.json"
        info = json.loads(info_path.read_text(encoding="utf-8"))
        captions = METADATA / f"{video_id}.en.vtt"
        cues = parse_vtt(captions)
        duration = float(info["duration"])
        video_path = VIDEOS / f"{video_id}.mp4"
        cuts = scene_times(video_path)
        boundaries = [0.0, *cuts, duration]
        intervals = [
            right - left
            for left, right in zip(boundaries, boundaries[1:])
            if right > left
        ]
        metrics = transcript_metrics(cues, duration)
        metrics.update(
            {
                "id": video_id,
                "title": info["title"],
                "url": info["webpage_url"],
                "upload_date": datetime.strptime(
                    info["upload_date"], "%Y%m%d"
                ).date().isoformat(),
                "duration_seconds": duration,
                "runtime": fmt_time(duration),
                "view_count": info.get("view_count"),
                "category": selected["category"],
                "selection_reason": selected["selection_reason"],
                "chapters": info.get("chapters") or [],
                "hard_cut_count_threshold_0_30": len(cuts),
                "hard_cuts_per_minute_threshold_0_30": round(
                    len(cuts) / max(duration / 60, 0.01), 1
                ),
                "mean_hard_cut_interval_seconds": round(
                    statistics.mean(intervals), 2
                )
                if intervals
                else duration,
                "median_hard_cut_interval_seconds": round(
                    statistics.median(intervals), 2
                )
                if intervals
                else duration,
                "hard_cut_timestamps": cuts,
            }
        )
        results.append(metrics)
        contact_sheets(video_path, video_id)
        print(f"analysed {video_id}: {info['title']}")

    aggregate = {
        "video_count": len(results),
        "total_runtime_seconds": sum(
            float(result["duration_seconds"]) for result in results
        ),
        "weighted_words_per_minute": round(
            sum(int(result["word_count"]) for result in results)
            / (
                sum(float(result["duration_seconds"]) for result in results)
                / 60
            ),
            1,
        ),
        "median_video_wpm": round(
            statistics.median(
                float(result["words_per_minute"]) for result in results
            ),
            1,
        ),
        "median_sentence_words": statistics.median(
            float(result["median_sentence_words"])
            for result in results
            if result["sentence_metrics_reliable"]
        ),
        "mean_hard_cuts_per_minute": round(
            statistics.mean(
                float(result["hard_cuts_per_minute_threshold_0_30"])
                for result in results
            ),
            1,
        ),
        "median_hard_cut_interval_seconds": round(
            statistics.median(
                float(result["median_hard_cut_interval_seconds"])
                for result in results
            ),
            2,
        ),
    }
    OUTPUT_JSON.write_text(
        json.dumps(
            {"aggregate": aggregate, "videos": results},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows = [
        "# How Money Works forensic corpus",
        "",
        (
            f"Analysed {aggregate['video_count']} videos "
            f"({fmt_time(aggregate['total_runtime_seconds'])} total)."
        ),
        "",
        "| # | Video | Published | Runtime | Category | WPM | Median sentence | Hard cuts/min* |",
        "|---:|---|---|---:|---|---:|---:|---:|",
    ]
    for index, result in enumerate(results, 1):
        rows.append(
            f"| {index} | [{result['title']}]({result['url']}) | "
            f"{result['upload_date']} | {result['runtime']} | "
            f"{result['category']} | {result['words_per_minute']} | "
            f"{result['median_sentence_words']} words"
            f"{'' if result['sentence_metrics_reliable'] else ' (unreliable captions)'} | "
            f"{result['hard_cuts_per_minute_threshold_0_30']} |"
        )
    rows.extend(
        [
            "",
            (
                "*Hard-cut count uses FFmpeg scene score > 0.30. It is a "
                "conservative measure of large visual changes and excludes many "
                "internal text/graphic events."
            ),
        ]
    )
    OUTPUT_MD.write_text("\n".join(rows) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
