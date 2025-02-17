# Highlight Video Maker

This script automatically creates a highlight reel from multiple video inputs by identifying and combining the loudest moments.

## How It Works

1. **Finds a Representative Video**

   - Chooses the shortest video as the "representative" video.

2. **Detects Loudest Moments**

   - Analyzes the representative video to find the 10 loudest segments.

3. **Applies to All Videos**

   - Uses the timestamps from the representative video to divide all others into clips.
     - Note: This will make all videos the same length, removing the excess content from the end.

4. **Combines Clips**

   - Merges the loudest segments using:
     - The representative video’s timestamps
     - A randomly selected perspective clip from the other videos

5. **Final Outputs**
   - A combonation of all vthe loudest clips, perspective randomly chosen
   - Same as above, but with a mobile-friendly vertical aspect ratio with blurred letterboxing
   - Both clips will be watermarked by an image input, with the image being slightly transparent
     on the standard video output and opaque on the mobile one

## CLI Options

All options except `--log-level` are required.

```
$ vr-video-maker --help
Usage: vr-video-maker [OPTIONS] COMMAND [ARGS]...

Options:
  --log-level Sets the logging verbosity. Choose betweenDEBUG, INFO (default), WARNING, ERROR, or CRITICAL.Can be uppercase or lowercase.
  --help                          Show this message and exit.

Commands:
  run  Main function that orchestrates the video processing pipeline.



$ vr-video-maker run --help
Usage: vr-video-maker run [OPTIONS]

  Main function that orchestrates the video processing pipeline.

Options:
  --input-dir The input directory to get the source videos from.
  --watermark-image The path of the watermark image to overlay over the final output. If not specified, no watermark will be applied. It will not be scaled, so it should be sized appropriately relative to the input.
  --horiz-output-file The path to output the final video to. It should not exist and must either be an absolute path or start with "./".
  --vert-output-file The path to output the final video to. It should not exist and must either be an absolute path or start with "./".
  --help                          Show this message and exit.
```

## Requirements

- **Operating System:** Linux (tested on Arch Linux, will not work on Windows-like systems)
- **Dependencies:** [FFmpeg](https://ffmpeg.org/) must be installed on the host system

## Temporary Storage

- The script uses `/tmp/video-maker-cache` for temporary files.
- This folder can be safely deleted after the script finishes running.
