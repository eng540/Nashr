"""Telegram upload contracts. Files remain private until an approved send."""
import re

MEDIA_METHODS = {
    "IMAGE": ("sendPhoto", "photo"), "VIDEO": ("sendVideo", "video"),
    "DOCUMENT": ("sendDocument", "document"), "AUDIO": ("sendAudio", "audio"),
    "ANIMATION": ("sendAnimation", "animation"), "VOICE": ("sendVoice", "voice"),
    "VIDEO_NOTE": ("sendVideoNote", "video_note"), "STICKER": ("sendSticker", "sticker"),
}
NO_CAPTION = frozenset({"VIDEO_NOTE", "STICKER"})


def media_request(kind, mime_type, data, filename=None):
    if kind not in MEDIA_METHODS or not data:
        raise ValueError("A non-empty supported media upload is required.")
    limit = (10 if kind == "IMAGE" else 50) * 1024 * 1024
    if len(data) > limit:
        raise ValueError(f"Telegram {kind} upload exceeds {limit} bytes.")
    allowed = {
        "IMAGE": {"image/png", "image/jpeg", "image/webp"}, "VIDEO": {"video/mp4"},
        "AUDIO": {"audio/mpeg", "audio/mp4"}, "ANIMATION": {"image/gif", "video/mp4"},
        "VOICE": {"audio/ogg", "audio/mpeg", "audio/mp4"}, "VIDEO_NOTE": {"video/mp4"},
        "STICKER": {"image/webp", "video/webm", "application/x-tgsticker"},
    }
    if kind != "DOCUMENT" and mime_type not in allowed[kind]:
        raise ValueError("Media MIME type does not match its Telegram method.")
    extensions = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp", "video/mp4": "mp4",
                  "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/ogg": "ogg", "image/gif": "gif",
                  "video/webm": "webm", "application/x-tgsticker": "tgs"}
    name = re.sub(r"[^A-Za-z0-9._-]", "-", filename or "").strip(".-")
    if not name:
        prefix = "nashr-card" if kind == "IMAGE" else "nashr-media"
        name = prefix + "." + extensions.get(mime_type, "bin")
    method, field = MEDIA_METHODS[kind]
    return method, field, name


def validate_special_media(kind, mime_type, data):
    """Validate the constraints that MIME signatures alone cannot establish."""
    if kind == "ANIMATION" and mime_type == "image/gif":
        return
    if kind not in {"VIDEO_NOTE", "STICKER", "ANIMATION"}:
        return
    if kind == "STICKER" and mime_type == "image/webp":
        import io
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if max(width, height) != 512 or min(width, height) > 512 or len(data) > 512 * 1024:
                raise ValueError("Static stickers need one512px side, at most512px on the other and512KiB.")
        return
    if kind == "STICKER" and mime_type == "application/x-tgsticker":
        import gzip
        import io
        import json
        if len(data) > 64 * 1024:
            raise ValueError("Animated sticker exceeds64KiB.")
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            raise ValueError("Expanded sticker exceeds its safe parsing limit.")
        payload = json.loads(raw)
        if payload.get("w") != 512 or payload.get("h") != 512 or payload.get("fr") not in {30, 60}:
            raise ValueError("Animated sticker must be512x512 at30or60fps.")
        if (payload.get("op", 0) - payload.get("ip", 0)) / payload["fr"] > 3:
            raise ValueError("Animated stickers must not exceed3seconds.")
        return
    import json
    import subprocess
    import tempfile
    with tempfile.NamedTemporaryFile() as file:
        file.write(data)
        file.flush()
        try:
            result = subprocess.run(["ffprobe", "-f", "matroska" if mime_type == "video/webm" else "mov", "-protocol_whitelist", "file,pipe", "-v", "error", "-show_streams", "-show_format", "-of", "json", file.name], capture_output=True, timeout=15, check=True)
            info = json.loads(result.stdout)
        except (OSError, subprocess.SubprocessError, ValueError) as exc:
            raise ValueError("Could not verify the video format and duration.") from exc
    videos = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    audio = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if not videos:
        raise ValueError("A video stream is required.")
    video = videos[0]
    try:
        duration = float(info.get("format", {}).get("duration", video.get("duration", 0)))
    except (TypeError, ValueError) as exc:
        raise ValueError("The video duration is unknown.") from exc
    if duration <= 0:
        raise ValueError("The video duration is unknown.")
    if kind == "VIDEO_NOTE" and (video.get("width") != video.get("height") or duration > 60 or video.get("codec_name") != "h264"):
        raise ValueError("Video notes must be square H.264 MP4 and at most60seconds.")
    if kind == "ANIMATION" and (audio or video.get("codec_name") != "h264"):
        raise ValueError("MP4 animations must be H.264 without audio.")
    if kind == "STICKER" and (duration > 3 or audio or video.get("codec_name") != "vp9" or max(video.get("width", 0), video.get("height", 0)) != 512 or len(data) > 256 * 1024):
        raise ValueError("Video stickers must be silent VP9 WebM up to3seconds,512px side and256KiB.")
