import os
import subprocess
import base64
import tempfile
from pathlib import Path

from app.utils import generate_uuid

class VideoPipeline:
    def __init__(self, llm_client):
        self.llm = llm_client
        # Back-compat alias
        self.nvidia = llm_client

    def process(self, video_path: str, doc_id: str,
                frame_interval_sec: int = 30) -> list[dict]:
        try:
            frames = self._extract_keyframes(video_path, frame_interval_sec)
        except (subprocess.SubprocessError, FileNotFoundError, Exception) as e:
            print(f"ffmpeg extraction failed or ffmpeg not installed: {e}. Using temporal metadata fallback.")
            return [
                {
                    "chunk_id": generate_uuid(f"video_{doc_id}_0"),
                    "modality": "video_frame",
                    "timestamp_sec": 0,
                    "base64": None,
                    "caption": "Video representation metadata. Keyframe extraction skipped because ffmpeg is not installed.",
                    "text_repr": f"[VIDEO] File {os.path.basename(video_path)} parsed. Configure ffmpeg in environment for frame extraction.",
                    "doc_id": doc_id,
                }
            ]

        chunks = []
        for i, (timestamp, b64_frame) in enumerate(frames):
            caption = self._caption_frame(b64_frame, timestamp)
            chunks.append({
                "chunk_id": generate_uuid(f"video_{doc_id}_{i}"),
                "modality": "video_frame",
                "timestamp_sec": timestamp,
                "base64": b64_frame,
                "caption": caption,
                "text_repr": f"[VIDEO at {timestamp}s] {caption}",
                "doc_id": doc_id,
            })
        return chunks

    def _extract_keyframes(self, path: str, interval: int) -> list[tuple]:
        """Use ffmpeg to extract 1 frame every N seconds."""
        with tempfile.TemporaryDirectory() as tmpdir:
            out_pattern = f"{tmpdir}/frame_%04d.jpg"
            # run ffmpeg command
            subprocess.run([
                "ffmpeg", "-i", path,
                "-vf", f"fps=1/{interval}",
                "-q:v", "2", out_pattern, "-y"
            ], capture_output=True, check=True)

            frames = []
            for frame_file in sorted(Path(tmpdir).glob("*.jpg")):
                idx = int(frame_file.stem.split("_")[1]) - 1
                timestamp = idx * interval
                b64 = base64.b64encode(frame_file.read_bytes()).decode()
                frames.append((timestamp, b64))
            return frames

    def _caption_frame(self, b64: str, timestamp: int) -> str:
        messages = [{
            "role": "user",
            "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text",
                 "text": f"This is a video frame at {timestamp} seconds. "
                         "Describe what is happening and any visible text/charts."}
            ]
        }]
        resp = self.llm.generate(messages, stream=False)
        return resp.content
