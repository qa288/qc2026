from __future__ import annotations

import json
import shutil
import struct
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Iterable


class VideoProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoProbeResult:
    source: str
    container: str
    coded_width: int
    coded_height: int
    display_width: int
    display_height: int
    rotation: int = 0
    sample_aspect_ratio: str = ""
    display_aspect_ratio: str = ""
    duration_seconds: float = 0.0
    bit_rate_bps: int = 0
    codec_name: str = ""
    pixel_format: str = ""
    profile: str = ""


@dataclass(frozen=True)
class _Box:
    kind: str
    start: int
    payload_start: int
    payload_end: int


def probe_video_file(file_path: Path) -> VideoProbeResult:
    path = Path(file_path)
    if not path.exists():
        raise VideoProbeError(f"file not found: {path}")
    probe_errors: list[str] = []
    for probe_fn in (_probe_with_ffprobe, _probe_with_mediainfo):
        try:
            probe_result = probe_fn(path)
        except VideoProbeError as exc:
            probe_errors.append(str(exc))
            continue
        if probe_result is not None:
            return probe_result
    signature = _read_signature(path)
    if _looks_like_iso_bmff(signature, path.suffix.lower()):
        return _probe_iso_bmff(path)
    if _looks_like_avi(signature, path.suffix.lower()):
        return _probe_avi(path)
    if probe_errors:
        raise VideoProbeError("; ".join(probe_errors))
    raise VideoProbeError(f"unsupported container for fallback probe: {path.suffix or '<none>'}")


def validate_video_probe_for_upload(
    result: VideoProbeResult,
    *,
    allowed_display_aspect_ratios: Iterable[str] | None = None,
    min_duration_seconds: float = 0.0,
    max_duration_seconds: float = 0.0,
    min_bitrate_bps: int = 0,
    allowed_containers: Iterable[str] | None = None,
    allowed_codecs: Iterable[str] | None = None,
) -> list[str]:
    problems: list[str] = []
    if result.coded_width <= 0 or result.coded_height <= 0:
        problems.append("\u65e0\u6cd5\u89e3\u6790\u7f16\u7801\u5c3a\u5bf8")
        return problems
    if result.coded_width % 2 != 0 or result.coded_height % 2 != 0:
        problems.append(
            f"\u7f16\u7801\u5c3a\u5bf8 {result.coded_width}x{result.coded_height} "
            "\u4e0d\u662f\u5076\u6570\u5bbd\u9ad8"
        )
    rotation = int(result.rotation or 0) % 360
    if rotation:
        problems.append(
            f"\u68c0\u6d4b\u5230\u65cb\u8f6c\u5143\u6570\u636e {rotation}\u00b0, "
            "\u63a5\u53e3\u53ef\u80fd\u6309\u7f16\u7801\u5c3a\u5bf8\u6821\u9a8c"
        )
    sar = str(result.sample_aspect_ratio or "").strip()
    if sar and sar != "1:1":
        problems.append(
            f"\u50cf\u7d20\u5bbd\u9ad8\u6bd4\u4e3a {sar}, \u4e0d\u662f 1:1"
        )
    if (
        result.display_width > 0
        and result.display_height > 0
        and (
            result.display_width != result.coded_width
            or result.display_height != result.coded_height
        )
    ):
        problems.append(
            f"\u663e\u793a\u5c3a\u5bf8 {result.display_width}x{result.display_height} "
            f"\u4e0e\u7f16\u7801\u5c3a\u5bf8 {result.coded_width}x{result.coded_height} "
            "\u4e0d\u4e00\u81f4"
        )
    display_aspect = _normalize_ratio_text(result.display_aspect_ratio) or _ratio_text(
        int(result.display_width or 0),
        int(result.display_height or 0),
    )
    allowed_aspects = {_normalize_ratio_text(item) for item in (allowed_display_aspect_ratios or [])}
    allowed_aspects.discard("")
    if allowed_aspects and display_aspect and display_aspect not in allowed_aspects:
        problems.append(
            f"\u663e\u793a\u5bbd\u9ad8\u6bd4 {display_aspect} \u4e0d\u5728\u5141\u8bb8\u8303\u56f4 "
            f"{', '.join(sorted(allowed_aspects))}"
        )
    dimension_problem = _official_video_dimension_problem(display_aspect, result.display_width, result.display_height)
    if dimension_problem:
        problems.append(dimension_problem)
    if min_duration_seconds > 0 and 0 < result.duration_seconds < min_duration_seconds:
        problems.append(
            f"\u65f6\u957f {result.duration_seconds:.2f}s \u4f4e\u4e8e {float(min_duration_seconds):.0f}s"
        )
    if max_duration_seconds > 0 and result.duration_seconds > max_duration_seconds:
        problems.append(
            f"\u65f6\u957f {result.duration_seconds:.2f}s \u8d85\u8fc7 {float(max_duration_seconds):.0f}s"
        )
    if min_bitrate_bps > 0 and result.bit_rate_bps > 0 and result.bit_rate_bps < min_bitrate_bps:
        problems.append(
            f"\u7801\u7387 {result.bit_rate_bps / 1000:.0f}kbps \u4f4e\u4e8e {int(min_bitrate_bps / 1000)}kbps"
        )
    normalized_container = str(result.container or "").strip().lower().lstrip(".")
    allowed_container_set = {
        str(item or "").strip().lower().lstrip(".")
        for item in (allowed_containers or [])
        if str(item or "").strip()
    }
    if allowed_container_set and normalized_container and normalized_container not in allowed_container_set:
        problems.append(f"\u5bb9\u5668 {normalized_container} \u4e0d\u5728\u5141\u8bb8\u8303\u56f4")
    normalized_codec = str(result.codec_name or "").strip().lower()
    allowed_codec_set = {
        str(item or "").strip().lower()
        for item in (allowed_codecs or [])
        if str(item or "").strip()
    }
    if allowed_codec_set and normalized_codec and normalized_codec not in allowed_codec_set:
        problems.append(f"\u7f16\u7801 {normalized_codec} \u4e0d\u5728\u5141\u8bb8\u8303\u56f4")
    return problems


def _official_video_dimension_problem(display_aspect: str, width: int, height: int) -> str:
    normalized_aspect = _normalize_ratio_text(display_aspect)
    normalized_width = int(width or 0)
    normalized_height = int(height or 0)
    if normalized_width <= 0 or normalized_height <= 0:
        return ""
    limits = {
        "16:9": (1280, 720, 2560, 1440),
        "9:16": (720, 1280, 1440, 2560),
    }
    limit = limits.get(normalized_aspect)
    if not limit:
        return ""
    min_width, min_height, max_width, max_height = limit
    if (
        normalized_width < min_width
        or normalized_height < min_height
        or normalized_width > max_width
        or normalized_height > max_height
    ):
        return (
            f"\u5206\u8fa8\u7387 {normalized_width}x{normalized_height} \u4e0d\u5728 "
            f"{min_width}x{min_height}-{max_width}x{max_height} \u8303\u56f4"
        )
    return ""


def format_video_probe_summary(result: VideoProbeResult) -> str:
    parts = [
        f"\u89c6\u9891\u5143\u6570\u636e: \u6765\u6e90={result.source}",
        f"\u5bb9\u5668={result.container or '-'}",
        f"\u7f16\u7801\u5c3a\u5bf8={result.coded_width}x{result.coded_height}",
        f"\u663e\u793a\u5c3a\u5bf8={result.display_width}x{result.display_height}",
    ]
    if result.rotation:
        parts.append(f"\u65cb\u8f6c={int(result.rotation) % 360}\u00b0")
    if result.sample_aspect_ratio:
        parts.append(f"SAR={result.sample_aspect_ratio}")
    if result.display_aspect_ratio:
        parts.append(f"DAR={result.display_aspect_ratio}")
    if result.duration_seconds > 0:
        parts.append(f"\u65f6\u957f={result.duration_seconds:.2f}s")
    if result.bit_rate_bps > 0:
        parts.append(f"\u7801\u7387={result.bit_rate_bps / 1000:.0f}kbps")
    if result.codec_name:
        parts.append(f"\u7f16\u7801={result.codec_name}")
    if result.pixel_format:
        parts.append(f"\u50cf\u7d20\u683c\u5f0f={result.pixel_format}")
    if result.profile:
        parts.append(f"profile={result.profile}")
    return ", ".join(parts)


def _probe_with_ffprobe(file_path: Path) -> VideoProbeResult | None:
    executable = shutil.which("ffprobe")
    if not executable:
        return None
    command = [
        executable,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(file_path),
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise VideoProbeError(f"ffprobe failed: {exc}") from exc
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise VideoProbeError("ffprobe returned invalid json") from exc
    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise VideoProbeError("ffprobe returned no stream list")
    video_stream = next(
        (
            item
            for item in streams
            if isinstance(item, dict) and str(item.get("codec_type") or "").strip() == "video"
        ),
        None,
    )
    if not isinstance(video_stream, dict):
        raise VideoProbeError("ffprobe returned no video stream")
    coded_width = _to_int(video_stream.get("coded_width")) or _to_int(video_stream.get("width"))
    coded_height = _to_int(video_stream.get("coded_height")) or _to_int(video_stream.get("height"))
    rotation = _extract_rotation(video_stream)
    sample_aspect_ratio = _normalize_ratio_text(video_stream.get("sample_aspect_ratio"))
    display_width, display_height = _compute_display_dimensions(
        coded_width,
        coded_height,
        sample_aspect_ratio,
        rotation,
    )
    display_aspect_ratio = _normalize_ratio_text(video_stream.get("display_aspect_ratio"))
    if not display_aspect_ratio and display_width > 0 and display_height > 0:
        display_aspect_ratio = _ratio_text(display_width, display_height)
    format_info = payload.get("format")
    duration_seconds = _to_float(video_stream.get("duration"))
    if duration_seconds <= 0:
        if isinstance(format_info, dict):
            duration_seconds = _to_float(format_info.get("duration"))
    bit_rate_bps = _parse_bitrate_bps(video_stream.get("bit_rate"))
    if bit_rate_bps <= 0 and isinstance(format_info, dict):
        bit_rate_bps = _parse_bitrate_bps(format_info.get("bit_rate"))
    if bit_rate_bps <= 0:
        bit_rate_bps = _estimate_bitrate_bps(file_path, duration_seconds)
    container = str(file_path.suffix.lower().lstrip(".") or "video")
    return VideoProbeResult(
        source="ffprobe",
        container=container,
        coded_width=coded_width,
        coded_height=coded_height,
        display_width=display_width,
        display_height=display_height,
        rotation=rotation,
        sample_aspect_ratio=sample_aspect_ratio,
        display_aspect_ratio=display_aspect_ratio,
        duration_seconds=duration_seconds,
        bit_rate_bps=bit_rate_bps,
        codec_name=str(video_stream.get("codec_name") or "").strip().lower(),
        pixel_format=str(video_stream.get("pix_fmt") or "").strip().lower(),
        profile=str(video_stream.get("profile") or "").strip(),
    )


def _probe_with_mediainfo(file_path: Path) -> VideoProbeResult | None:
    executable = shutil.which("mediainfo")
    if not executable:
        return None
    command = [executable, "--Output=JSON", str(file_path)]
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise VideoProbeError(f"mediainfo failed: {exc}") from exc
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise VideoProbeError("mediainfo returned invalid json") from exc
    media = payload.get("media")
    tracks = media.get("track") if isinstance(media, dict) else None
    if not isinstance(tracks, list):
        raise VideoProbeError("mediainfo returned no track list")
    video_track = next(
        (
            item
            for item in tracks
            if isinstance(item, dict) and str(item.get("@type") or "").strip().lower() == "video"
        ),
        None,
    )
    if not isinstance(video_track, dict):
        raise VideoProbeError("mediainfo returned no video track")
    coded_width = _to_int(video_track.get("Width"))
    coded_height = _to_int(video_track.get("Height"))
    rotation = _normalize_rotation(video_track.get("Rotation"))
    sample_aspect_ratio = _normalize_ratio_text(video_track.get("PixelAspectRatio")) or "1:1"
    display_width, display_height = _compute_display_dimensions(
        coded_width,
        coded_height,
        sample_aspect_ratio,
        rotation,
    )
    display_aspect_ratio = _normalize_ratio_text(video_track.get("DisplayAspectRatio"))
    if not display_aspect_ratio and display_width > 0 and display_height > 0:
        display_aspect_ratio = _ratio_text(display_width, display_height)
    duration_seconds = _parse_duration_seconds(video_track.get("Duration"))
    container = str(file_path.suffix.lower().lstrip(".") or "video")
    bit_rate_bps = (
        _parse_bitrate_bps(video_track.get("BitRate"))
        or _parse_bitrate_bps(video_track.get("BitRate/String"))
        or _parse_bitrate_bps(video_track.get("Bit rate"))
        or _estimate_bitrate_bps(file_path, duration_seconds)
    )
    return VideoProbeResult(
        source="mediainfo",
        container=container,
        coded_width=coded_width,
        coded_height=coded_height,
        display_width=display_width,
        display_height=display_height,
        rotation=rotation,
        sample_aspect_ratio=sample_aspect_ratio,
        display_aspect_ratio=display_aspect_ratio,
        duration_seconds=duration_seconds,
        bit_rate_bps=bit_rate_bps,
        codec_name=_normalize_mediainfo_codec(video_track),
        pixel_format=str(video_track.get("PixelFormat") or "").strip().lower(),
        profile=str(video_track.get("Format_Profile") or video_track.get("Format profile") or "").strip(),
    )


def _probe_iso_bmff(file_path: Path) -> VideoProbeResult:
    with file_path.open("rb") as handle:
        file_size = file_path.stat().st_size
        moov_box = next((box for box in _iter_boxes(handle, 0, file_size) if box.kind == "moov"), None)
        if moov_box is None:
            raise VideoProbeError("mp4 fallback probe could not find moov box")
        for trak_box in _iter_boxes(handle, moov_box.payload_start, moov_box.payload_end):
            if trak_box.kind != "trak":
                continue
            track = _parse_mp4_track(handle, trak_box)
            if track and track["is_video"]:
                coded_width = int(track.get("coded_width") or 0)
                coded_height = int(track.get("coded_height") or 0)
                sample_aspect_ratio = str(track.get("sample_aspect_ratio") or "").strip() or "1:1"
                rotation = int(track.get("rotation") or 0)
                display_width = int(track.get("display_width") or 0)
                display_height = int(track.get("display_height") or 0)
                if display_width <= 0 or display_height <= 0:
                    display_width, display_height = _compute_display_dimensions(
                        coded_width,
                        coded_height,
                        sample_aspect_ratio,
                        rotation,
                    )
                display_aspect_ratio = str(track.get("display_aspect_ratio") or "").strip()
                if not display_aspect_ratio and display_width > 0 and display_height > 0:
                    display_aspect_ratio = _ratio_text(display_width, display_height)
                duration_seconds = float(track.get("duration_seconds") or 0.0)
                return VideoProbeResult(
                    source="iso-bmff-fallback",
                    container=str(file_path.suffix.lower().lstrip(".") or "mp4"),
                    coded_width=coded_width,
                    coded_height=coded_height,
                    display_width=display_width,
                    display_height=display_height,
                    rotation=rotation,
                    sample_aspect_ratio=sample_aspect_ratio,
                    display_aspect_ratio=display_aspect_ratio,
                    duration_seconds=duration_seconds,
                    bit_rate_bps=_estimate_bitrate_bps(file_path, duration_seconds),
                    codec_name=str(track.get("codec_name") or "").strip().lower(),
                )
    raise VideoProbeError("mp4 fallback probe returned no video track")


def _parse_mp4_track(handle, trak_box: _Box) -> dict[str, object] | None:
    track: dict[str, object] = {
        "is_video": False,
        "coded_width": 0,
        "coded_height": 0,
        "display_width": 0,
        "display_height": 0,
        "rotation": 0,
        "sample_aspect_ratio": "",
        "display_aspect_ratio": "",
        "duration_seconds": 0.0,
    }
    handler_type = ""
    for child in _iter_boxes(handle, trak_box.payload_start, trak_box.payload_end):
        if child.kind == "tkhd":
            track.update(_parse_mp4_tkhd(handle, child))
        elif child.kind == "mdia":
            parsed = _parse_mp4_mdia(handle, child)
            handler_type = str(parsed.get("handler_type") or "")
            track.update(parsed)
    if handler_type == "vide" or (int(track.get("coded_width") or 0) > 0 and int(track.get("coded_height") or 0) > 0):
        track["is_video"] = True
        return track
    return None


def _parse_mp4_tkhd(handle, box: _Box) -> dict[str, object]:
    data = _read_box_payload(handle, box)
    if len(data) < 84:
        return {}
    version = data[0]
    if version == 1:
        matrix_offset = 52
    else:
        matrix_offset = 40
    if len(data) < matrix_offset + 44:
        return {}
    matrix = struct.unpack(">9i", data[matrix_offset:matrix_offset + 36])
    width_fixed, height_fixed = struct.unpack(">II", data[matrix_offset + 36:matrix_offset + 44])
    return {
        "display_width": _fixed_16_16_to_int(width_fixed),
        "display_height": _fixed_16_16_to_int(height_fixed),
        "rotation": _rotation_from_matrix(matrix),
    }


def _parse_mp4_mdia(handle, mdia_box: _Box) -> dict[str, object]:
    parsed: dict[str, object] = {}
    for child in _iter_boxes(handle, mdia_box.payload_start, mdia_box.payload_end):
        if child.kind == "hdlr":
            parsed["handler_type"] = _parse_mp4_hdlr(handle, child)
        elif child.kind == "mdhd":
            parsed["duration_seconds"] = _parse_mp4_mdhd(handle, child)
        elif child.kind == "minf":
            parsed.update(_parse_mp4_minf(handle, child))
    return parsed


def _parse_mp4_hdlr(handle, box: _Box) -> str:
    data = _read_box_payload(handle, box)
    if len(data) < 12:
        return ""
    return data[8:12].decode("latin1", errors="ignore")


def _parse_mp4_mdhd(handle, box: _Box) -> float:
    data = _read_box_payload(handle, box)
    if len(data) < 24:
        return 0.0
    version = data[0]
    if version == 1:
        if len(data) < 32:
            return 0.0
        timescale = struct.unpack(">I", data[20:24])[0]
        duration = struct.unpack(">Q", data[24:32])[0]
    else:
        timescale = struct.unpack(">I", data[12:16])[0]
        duration = struct.unpack(">I", data[16:20])[0]
    if timescale <= 0:
        return 0.0
    return round(float(duration) / float(timescale), 3)


def _parse_mp4_minf(handle, minf_box: _Box) -> dict[str, object]:
    for child in _iter_boxes(handle, minf_box.payload_start, minf_box.payload_end):
        if child.kind == "stbl":
            return _parse_mp4_stbl(handle, child)
    return {}


def _parse_mp4_stbl(handle, stbl_box: _Box) -> dict[str, object]:
    for child in _iter_boxes(handle, stbl_box.payload_start, stbl_box.payload_end):
        if child.kind == "stsd":
            return _parse_mp4_stsd(handle, child)
    return {}


def _parse_mp4_stsd(handle, box: _Box) -> dict[str, object]:
    data = _read_box_payload(handle, box)
    if len(data) < 16:
        return {}
    entry_count = struct.unpack(">I", data[4:8])[0]
    offset = 8
    for _ in range(entry_count):
        if offset + 8 > len(data):
            break
        entry_size = struct.unpack(">I", data[offset:offset + 4])[0]
        if entry_size < 8 or offset + entry_size > len(data):
            break
        entry_kind = data[offset + 4:offset + 8].decode("latin1", errors="ignore")
        entry_payload = data[offset + 8:offset + entry_size]
        parsed = _parse_mp4_visual_sample_entry(entry_payload, entry_kind)
        if parsed:
            return parsed
        offset += entry_size
    return {}


def _parse_mp4_visual_sample_entry(entry_payload: bytes, entry_kind: str = "") -> dict[str, object]:
    if len(entry_payload) < 28:
        return {}
    coded_width, coded_height = struct.unpack(">HH", entry_payload[24:28])
    sample_aspect_ratio = ""
    if len(entry_payload) >= 86:
        for child in _iter_box_bytes(entry_payload, 78, len(entry_payload)):
            if child.kind != "pasp":
                continue
            start = child.payload_start
            end = child.payload_end
            if end - start < 8:
                continue
            h_spacing, v_spacing = struct.unpack(">II", entry_payload[start:start + 8])
            sample_aspect_ratio = _ratio_text(h_spacing, v_spacing)
            break
    return {
        "coded_width": int(coded_width),
        "coded_height": int(coded_height),
        "sample_aspect_ratio": sample_aspect_ratio or "1:1",
        "codec_name": str(entry_kind or "").strip().lower(),
    }


def _probe_avi(file_path: Path) -> VideoProbeResult:
    with file_path.open("rb") as handle:
        signature = handle.read(12)
        if len(signature) < 12 or signature[:4] != b"RIFF" or signature[8:12] != b"AVI ":
            raise VideoProbeError("avi fallback probe found invalid header")
        file_size = file_path.stat().st_size
        duration_seconds = 0.0
        for chunk_kind, payload_start, payload_end, list_type in _iter_riff_chunks(handle, 12, file_size):
            if chunk_kind == "avih":
                duration_seconds = _parse_avi_avih(handle, payload_start, payload_end)
            if chunk_kind != "LIST" or list_type != "hdrl":
                continue
            video_track = _parse_avi_hdrl(handle, payload_start, payload_end)
            if video_track:
                coded_width = int(video_track.get("coded_width") or 0)
                coded_height = int(video_track.get("coded_height") or 0)
                return VideoProbeResult(
                    source="avi-fallback",
                    container="avi",
                    coded_width=coded_width,
                    coded_height=coded_height,
                    display_width=coded_width,
                    display_height=coded_height,
                    rotation=0,
                    sample_aspect_ratio="1:1",
                    display_aspect_ratio=_ratio_text(coded_width, coded_height),
                    duration_seconds=duration_seconds,
                    bit_rate_bps=_estimate_bitrate_bps(file_path, duration_seconds),
                    codec_name=str(video_track.get("codec_name") or "").strip().lower(),
                )
    raise VideoProbeError("avi fallback probe returned no video stream")


def _parse_avi_hdrl(handle, start: int, end: int) -> dict[str, int] | None:
    for chunk_kind, payload_start, payload_end, list_type in _iter_riff_chunks(handle, start, end):
        if chunk_kind != "LIST" or list_type != "strl":
            continue
        current_type = ""
        width = 0
        height = 0
        for sub_kind, sub_start, sub_end, sub_list_type in _iter_riff_chunks(handle, payload_start, payload_end):
            if sub_kind == "strh":
                current_type = _parse_avi_strh(handle, sub_start, sub_end)
            elif sub_kind == "strf" and current_type == "vids":
                width, height = _parse_avi_strf(handle, sub_start, sub_end)
        if current_type == "vids" and width > 0 and height > 0:
            return {"coded_width": width, "coded_height": height}
    return None


def _parse_avi_strh(handle, start: int, end: int) -> str:
    handle.seek(start)
    data = handle.read(min(8, end - start))
    if len(data) < 4:
        return ""
    return data[:4].decode("latin1", errors="ignore")


def _parse_avi_strf(handle, start: int, end: int) -> tuple[int, int]:
    handle.seek(start)
    data = handle.read(min(40, end - start))
    if len(data) < 12:
        return 0, 0
    width = struct.unpack("<i", data[4:8])[0]
    height = struct.unpack("<i", data[8:12])[0]
    return abs(int(width)), abs(int(height))


def _normalize_mediainfo_codec(video_track: dict[str, object]) -> str:
    candidates = [
        video_track.get("CodecID"),
        video_track.get("CodecID/Hint"),
        video_track.get("Format"),
    ]
    text = " ".join(str(item or "") for item in candidates).lower()
    if "avc" in text or "h.264" in text or "h264" in text:
        return "h264"
    if "hev" in text or "h.265" in text or "h265" in text:
        return "hevc"
    return str(video_track.get("Format") or "").strip().lower()


def _parse_avi_avih(handle, start: int, end: int) -> float:
    handle.seek(start)
    data = handle.read(min(56, end - start))
    if len(data) < 20:
        return 0.0
    microseconds_per_frame = struct.unpack("<I", data[0:4])[0]
    total_frames = struct.unpack("<I", data[16:20])[0]
    if microseconds_per_frame <= 0 or total_frames <= 0:
        return 0.0
    return round((microseconds_per_frame * total_frames) / 1_000_000.0, 3)


def _iter_boxes(handle, start: int, end: int):
    cursor = start
    while cursor + 8 <= end:
        handle.seek(cursor)
        header = handle.read(8)
        if len(header) < 8:
            return
        size = struct.unpack(">I", header[:4])[0]
        kind = header[4:8].decode("latin1", errors="ignore")
        header_size = 8
        if size == 1:
            large_size_data = handle.read(8)
            if len(large_size_data) < 8:
                return
            size = struct.unpack(">Q", large_size_data)[0]
            header_size = 16
        elif size == 0:
            size = end - cursor
        if size < header_size:
            return
        payload_start = cursor + header_size
        payload_end = min(cursor + size, end)
        yield _Box(kind=kind, start=cursor, payload_start=payload_start, payload_end=payload_end)
        next_cursor = cursor + size
        if next_cursor <= cursor:
            return
        cursor = next_cursor


def _iter_box_bytes(data: bytes, start: int, end: int):
    cursor = start
    limit = min(len(data), end)
    while cursor + 8 <= limit:
        size = struct.unpack(">I", data[cursor:cursor + 4])[0]
        kind = data[cursor + 4:cursor + 8].decode("latin1", errors="ignore")
        header_size = 8
        if size == 1:
            if cursor + 16 > limit:
                return
            size = struct.unpack(">Q", data[cursor + 8:cursor + 16])[0]
            header_size = 16
        elif size == 0:
            size = limit - cursor
        if size < header_size:
            return
        payload_start = cursor + header_size
        payload_end = min(cursor + size, limit)
        yield _Box(kind=kind, start=cursor, payload_start=payload_start, payload_end=payload_end)
        next_cursor = cursor + size
        if next_cursor <= cursor:
            return
        cursor = next_cursor


def _iter_riff_chunks(handle, start: int, end: int):
    cursor = start
    while cursor + 8 <= end:
        handle.seek(cursor)
        header = handle.read(8)
        if len(header) < 8:
            return
        kind = header[:4].decode("latin1", errors="ignore")
        size = struct.unpack("<I", header[4:8])[0]
        payload_start = cursor + 8
        payload_end = min(payload_start + size, end)
        list_type = ""
        if kind == "LIST":
            handle.seek(payload_start)
            list_header = handle.read(4)
            if len(list_header) < 4:
                return
            list_type = list_header.decode("latin1", errors="ignore")
            payload_start += 4
        yield kind, payload_start, payload_end, list_type
        cursor = payload_end + (size % 2)


def _read_box_payload(handle, box: _Box) -> bytes:
    handle.seek(box.payload_start)
    return handle.read(max(0, box.payload_end - box.payload_start))


def _read_signature(file_path: Path) -> bytes:
    with file_path.open("rb") as handle:
        return handle.read(32)


def _looks_like_iso_bmff(signature: bytes, suffix: str) -> bool:
    if suffix in {".mp4", ".m4v", ".mov", ".3gp", ".3gpp"}:
        return True
    if len(signature) >= 8 and signature[4:8] in {b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip"}:
        return True
    return False


def _looks_like_avi(signature: bytes, suffix: str) -> bool:
    if suffix == ".avi":
        return True
    return len(signature) >= 12 and signature[:4] == b"RIFF" and signature[8:12] == b"AVI "


def _compute_display_dimensions(
    coded_width: int,
    coded_height: int,
    sample_aspect_ratio: str,
    rotation: int,
) -> tuple[int, int]:
    if coded_width <= 0 or coded_height <= 0:
        return 0, 0
    sar = _parse_ratio(sample_aspect_ratio) or Fraction(1, 1)
    display_width = int(round(coded_width * float(sar)))
    display_height = int(coded_height)
    if int(rotation or 0) % 360 in {90, 270}:
        display_width, display_height = display_height, display_width
    return display_width, display_height


def _extract_rotation(stream_payload: dict[str, object]) -> int:
    tags = stream_payload.get("tags")
    if isinstance(tags, dict):
        rotation = _normalize_rotation(tags.get("rotate"))
        if rotation:
            return rotation
    side_data_list = stream_payload.get("side_data_list")
    if isinstance(side_data_list, list):
        for item in side_data_list:
            if not isinstance(item, dict):
                continue
            rotation = _normalize_rotation(item.get("rotation"))
            if rotation:
                return rotation
    return 0


def _normalize_rotation(value: object) -> int:
    try:
        rotation = int(round(float(str(value).strip())))
    except (TypeError, ValueError):
        return 0
    rotation %= 360
    normalized = rotation % 90
    if normalized:
        return rotation
    return rotation


def _rotation_from_matrix(matrix: tuple[int, ...]) -> int:
    if len(matrix) < 4:
        return 0
    a, b, c, d = (_matrix_sign(matrix[0]), _matrix_sign(matrix[1]), _matrix_sign(matrix[3]), _matrix_sign(matrix[4]))
    if (a, b, c, d) == (1, 0, 0, 1):
        return 0
    if (a, b, c, d) == (0, 1, -1, 0):
        return 90
    if (a, b, c, d) == (-1, 0, 0, -1):
        return 180
    if (a, b, c, d) == (0, -1, 1, 0):
        return 270
    return 0


def _matrix_sign(value: int) -> int:
    if value > 32768:
        return 1
    if value < -32768:
        return -1
    return 0


def _fixed_16_16_to_int(value: int) -> int:
    return int(round(float(value) / 65536.0))


def _normalize_ratio_text(value: object) -> str:
    text = str(value or "").strip()
    if not text or text.upper() == "N/A":
        return ""
    if ":" in text:
        return _ratio_text(*_parse_ratio_parts(text))
    if "/" in text:
        numerator, denominator = text.split("/", 1)
        return _ratio_text(_to_int(numerator), _to_int(denominator))
    try:
        fraction = Fraction(str(float(text))).limit_denominator(1000)
    except (TypeError, ValueError):
        return ""
    return _ratio_text(fraction.numerator, fraction.denominator)


def _parse_ratio_parts(text: str) -> tuple[int, int]:
    left, right = text.split(":", 1)
    return _to_int(left), _to_int(right)


def _parse_ratio(text: str) -> Fraction | None:
    normalized = _normalize_ratio_text(text)
    if not normalized:
        return None
    numerator, denominator = normalized.split(":", 1)
    numerator_value = _to_int(numerator)
    denominator_value = _to_int(denominator)
    if numerator_value <= 0 or denominator_value <= 0:
        return None
    return Fraction(numerator_value, denominator_value)


def _ratio_text(numerator: int, denominator: int) -> str:
    numerator_value = int(numerator or 0)
    denominator_value = int(denominator or 0)
    if numerator_value <= 0 or denominator_value <= 0:
        return ""
    fraction = Fraction(numerator_value, denominator_value)
    return f"{fraction.numerator}:{fraction.denominator}"


def _parse_duration_seconds(value: object) -> float:
    numeric = _to_float(value)
    if numeric > 0:
        return numeric / 1000.0 if numeric > 1000 else numeric
    text = str(value or "").strip().lower()
    if text.endswith(" ms"):
        return _to_float(text[:-3]) / 1000.0
    if text.endswith(" s"):
        return _to_float(text[:-2])
    return 0.0


def _parse_bitrate_bps(value: object) -> int:
    text = str(value or "").strip().lower()
    if not text or text == "n/a":
        return 0
    numeric_text = "".join(char for char in text if char.isdigit() or char in ".")
    if not numeric_text:
        return 0
    try:
        numeric = float(numeric_text)
    except ValueError:
        return 0
    if numeric <= 0:
        return 0
    if "mb/s" in text or "mbps" in text or "mib/s" in text:
        return int(round(numeric * 1_000_000))
    if "kb/s" in text or "kbps" in text or "kib/s" in text:
        return int(round(numeric * 1_000))
    return int(round(numeric))


def _estimate_bitrate_bps(file_path: Path, duration_seconds: float) -> int:
    try:
        duration = float(duration_seconds or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    if duration <= 0:
        return 0
    try:
        size = int(Path(file_path).stat().st_size)
    except OSError:
        return 0
    if size <= 0:
        return 0
    return int(round(size * 8 / duration))


def _to_int(value: object) -> int:
    if value is None:
        return 0
    text = str(value).strip()
    if not text:
        return 0
    digits = []
    for char in text:
        if char.isdigit() or (char == "-" and not digits):
            digits.append(char)
        elif digits:
            break
    if not digits or digits == ["-"]:
        return 0
    try:
        return int("".join(digits))
    except ValueError:
        return 0


def _to_float(value: object) -> float:
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0
