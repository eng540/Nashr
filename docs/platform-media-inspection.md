# Explicit read-only media inspection

Verified 2026-11-24 against Meta IG User Media reference:
https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/

The editor can read an approved original from private storage, at most 50 MiB. It does not convert, crop, compress, expose a media URL, change metadata, store a pass, schedule or send. The response identifies the original fingerprint, inspected bytes hash, copy version and time. Source changes during a read invalidate it. Missing ffprobe, malformed media or a bounded read failure never counts as success.

Image measurements come from Pillow. Instagram checks actual JPEG, size at most 8 million bytes and aspect ratio 0.8 through 1.91. Meta may resize widths outside 320 through 1440 and convert color to sRGB. We report that separately, without changing originals.

MP4/MOV video measurements come from ffprobe with a forced MOV demuxer and restricted protocols. Instagram checks measured codec, chroma format, progressive scan when declared, frame rate 23 through 60, 3 through 900 seconds, width at most 1920, ratio 0.01 through 10, declared video bitrate at most 25 million bits/s and available audio stream properties. Missing declared measurements remain pending. We do not claim to verify front-loaded moov, edit lists, closed GOP, variable bitrate or audio bitrate. The app read cap is deliberately below Meta's 300MB maximum and is not a platform limit.

YouTube and other platforms receive measurements only, not an official media-compatibility verdict. Field checks, account/app grants, platform acceptance and publication authority remain separate for every platform. No status from this read means ready to publish.
