"""Validate the motion half of Telegram sendLivePhoto uploads."""

def validate_live_motion(data):
    if not isinstance(data, bytes) or not data or len(data) > 10 * 1024 * 1024 or data[4:8] != b'ftyp':
        raise ValueError('Live Photo motion must be an MP4 up to10MiB.')
    import json, math, subprocess, tempfile
    with tempfile.NamedTemporaryFile() as file:
        file.write(data); file.flush()
        try:
            result = subprocess.run(['ffprobe', '-f', 'mov', '-protocol_whitelist', 'file,pipe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', file.name], capture_output=True, timeout=15, check=True)
            info = json.loads(result.stdout)
            duration = float(info.get('format', {}).get('duration', 0))
        except (OSError, subprocess.SubprocessError, ValueError, TypeError) as exc:
            raise ValueError('Could not verify Live Photo motion format.') from exc
    videos = [v for v in info.get('streams', []) if v.get('codec_type') == 'video']
    if len(videos) != 1 or videos[0].get('codec_name') != 'h264' or not math.isfinite(duration) or not 0 < duration <= 10:
        raise ValueError('Live Photo motion must contain one H264 video stream up to10seconds.')
