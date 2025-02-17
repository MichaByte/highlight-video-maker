import concurrent.futures
from logging import Logger, getLevelNamesMapping
import math
import random
import subprocess
from collections import Counter
from pathlib import Path
from typing import Dict, List

import click

from .logger import get_logger

logger: Logger


@click.group()
@click.option(
    "--log-level",
    default="INFO",
    type=str,
    required=False,
    metavar="Sets the logging verbosity. Choose between"
    "DEBUG, INFO (default), WARNING, ERROR, or CRITICAL."
    "Can be uppercase or lowercase.",
)
def cli(log_level: str):
    global logger
    try:
        level_from_name = getLevelNamesMapping()[log_level.upper()]
        logger = get_logger(level_from_name)
    except Exception as e:
        logger.exception(e)


IN_DIR: Path
OUT_DIR: Path
CACHE_DIR = Path("/tmp/video-maker-cache")
THREADS = 16

MIN_SEGMENT_LENGTH = 3.5
MAX_SEGMENT_LENGTH = 7.5
MAX_SEGMENT_PADDING = 6


def seconds_to_timestamp(seconds: float):
    """Converts total seconds to a timestamp (HH:MM:SS.ms)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 100)
    return f"{hours:02}:{minutes:02}:{secs:02}.{millis:02}"


def get_video_duration(file: Path):
    """Gets the duration of a video file in seconds."""
    logger.debug(f"Getting file length for {file}")
    try:
        return float(
            subprocess.run(
                f'ffprobe -v error -show_entries format=duration -of csv=p=0 "{file}"',
                capture_output=True,
                check=True,
                text=True,
                shell=True,
            ).stdout.strip()
        )
    except Exception:
        logger.exception(f"Error getting file length for {file}")
        return 0.0


def generate_segment_lengths(file_length: float) -> List[float]:
    """Generates random segment lengths that sum up to the file length."""
    segment_lengths: List[float] = []
    while not math.isclose(sum(segment_lengths), file_length, rel_tol=1e-5):
        remaining_length = file_length - sum(segment_lengths)
        if remaining_length <= MAX_SEGMENT_PADDING:
            segment_lengths.append(remaining_length)
            break
        segment_lengths.append(
            random.uniform(
                MIN_SEGMENT_LENGTH, min(MAX_SEGMENT_LENGTH, remaining_length)
            )
        )
    logger.debug(f"Generated segment lengths: {segment_lengths}")
    return segment_lengths


def split_video_segment(
    segment_lengths: List[float],
    file_name: Path,
    idx: int,
    out_dir: Path = Path(CACHE_DIR),
):
    """Splits a video into segments using ffmpeg."""
    logger.debug(f"Splitting {file_name} - segment {idx}")
    subprocess.run(
        f"ffmpeg -nostats -loglevel 0  -y -ss {seconds_to_timestamp(sum(segment_lengths[:idx]))} "
        f'-to {seconds_to_timestamp(sum(segment_lengths[:idx]) + segment_lengths[idx])} -i "{file_name}" '
        f'-c copy "{Path(out_dir, file_name.stem, str(idx) + file_name.suffix)}"',
        check=True,
        shell=True,
    )


def get_amplitude_of_segment(clip: Path):
    """Extracts the mean audio amplitude of a video segment."""
    logger.debug(f"Analyzing amplitude for clip: {clip}")
    res = subprocess.run(
        f'ffmpeg -i "{Path(CACHE_DIR, clip)}" -filter:a volumedetect -f null -',
        shell=True,
        check=True,
        capture_output=True,
    ).stderr
    return float(res.decode().split("mean_volume: ")[1].split(" dB")[0])


@cli.command()
@click.option(
    "--input-dir",
    metavar="The input directory to get the source videos from.",
    type=click.Path(exists=True, resolve_path=True, path_type=Path),
)
@click.option(
    "--watermark-image",
    metavar="The path of the watermark image "
    "to overlay over the final output. "
    "It must exist. "
    "It will not be scaled, so it should be "
    "sized appropriately relative to the input.",
    type=click.Path(exists=True, resolve_path=True, path_type=Path),
)
@click.option(
    "--horiz-output-file",
    metavar="The path to output the final video to. "
    "It should not exist and must either be an absolute path "
    'or start with "./".',
    type=click.Path(exists=False, resolve_path=True, path_type=Path),
)
@click.option(
    "--vert-output-file",
    metavar="The path to output the final video to. "
    "It should not exist and must either be an absolute path "
    'or start with "./".',
    type=click.Path(exists=False, resolve_path=True, path_type=Path),
)
def run(
    input_dir: Path,
    watermark_image: Path,
    horiz_output_file: Path,
    vert_output_file: Path,
):
    """Main function that orchestrates the video processing pipeline."""
    logger.info("Starting video processing pipeline.")
    raw_videos = next(input_dir.walk())

    representative_video = min(
        (Path(raw_videos[0], p) for p in raw_videos[2]), key=get_video_duration
    )

    logger.info(f"The representative video is: {representative_video}")

    representative_video_segments = generate_segment_lengths(
        get_video_duration(representative_video)
    )

    for vid in raw_videos[2]:
        Path(CACHE_DIR, Path(vid).stem).resolve().mkdir(parents=True, exist_ok=True)

    # Splitting videos into segments using multiprocessing
    with concurrent.futures.ProcessPoolExecutor(max_workers=THREADS) as split_executor:
        try:
            Path(CACHE_DIR, representative_video.stem).mkdir(
                parents=True, exist_ok=True
            )
        except FileExistsError:
            pass
        for idx in range(len(representative_video_segments)):
            for vid in raw_videos[2]:
                split_executor.submit(
                    split_video_segment,
                    representative_video_segments,
                    Path(raw_videos[0], vid).resolve(),
                    idx,
                )

    # Computing amplitude for each segment
    representative_video_audio_futures: Dict[str, concurrent.futures.Future[float]] = {}

    with concurrent.futures.ProcessPoolExecutor(
        max_workers=THREADS
    ) as amplitude_executor:
        for split_vid in next(Path(CACHE_DIR, Path(representative_video).stem).walk())[
            2
        ]:
            representative_video_audio_futures[split_vid] = amplitude_executor.submit(
                get_amplitude_of_segment,
                Path(CACHE_DIR, Path(representative_video).stem, split_vid).resolve(),
            )

    representative_video_audio_levels: Dict[str, float] = {}
    # Collecting results
    for seg in representative_video_audio_futures.keys():
        representative_video_audio_levels[seg] = representative_video_audio_futures[
            seg
        ].result()

    highest = dict(Counter(representative_video_audio_levels).most_common(10))
    loudest_seg_indexes: List[int] = [int(str(Path(k).stem)) for k in highest.keys()]

    for video in raw_videos[2]:
        out_folder = Path(CACHE_DIR, "loudest", Path(video).stem)
        out_folder.mkdir(parents=True, exist_ok=True)
        for seg in loudest_seg_indexes:
            split_video_segment(
                representative_video_segments,
                Path(raw_videos[0], video),
                seg,
                out_folder.parent,
            )

    with open(str(Path(CACHE_DIR, "list.txt")), "w") as f:
        for seg in loudest_seg_indexes:
            random_seg = Path(random.choice(raw_videos[2]))
            f.write(
                f"file '{Path(CACHE_DIR, "loudest", random_seg.stem, str(seg) + random_seg.suffix)}'\n"
            )


    logger.info("Creating horizontal video...")
    # Horizontal Pipeline: Concatenate clips and overlay a semi‑transparent watermark.
    subprocess.run(
        f'''ffmpeg -y -f concat -safe 0 -i "{Path(CACHE_DIR, "list.txt")}" -i "{watermark_image}" \
    -filter_complex "
    [1]format=rgba,colorchannelmixer=aa=0.5[logo];
    [0][logo]overlay=W-w-30:H-h-30:format=auto,format=yuv420p
    " -c:a copy "{horiz_output_file}"''',
        shell=True,
        check=True,
        capture_output=True,
    )

    logger.info("Creating vertical video...")
    # Vertical Pipeline: Concatenate, crop (zoom), split & blur for a vertical aspect ratio,
    # then overlay a centered, opaque watermark at the bottom.
    subprocess.run(
        f'''ffmpeg -y -f concat -safe 0 -i "{Path(CACHE_DIR, "list.txt")}" -i "{watermark_image}" \
    -filter_complex "
    [0]crop=3/4*in_w:in_h[zoomed];
    [zoomed]split[original][copy];
    [copy]scale=-1:ih*(4/3)*(4/3),crop=w=ih*9/16,gblur=sigma=17:steps=5[blurred];
    [blurred][original]overlay=(main_w-overlay_w)/2:(main_h-overlay_h)/2[vert];
    [vert][1]overlay=(W-w)/2:H-h-30,format=yuv420p
    " -c:a copy "{vert_output_file}"''',
        shell=True,
        check=True,
        capture_output=True,
    )

    logger.info("Video processing pipeline completed.")


if __name__ == "__main__":
    cli()
