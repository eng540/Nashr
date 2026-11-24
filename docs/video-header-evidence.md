# Bounded video-header evidence

2026-11-24. Read-only preparation, no conversion, schedule or original mutation.

H.264 uses a complete bounded FFmpeg trace_headers pass in stream-copy mode. A positive refresh-boundary finding requires the first slice to be IDR, every intra slice to occur in an IDR NAL and no unsupported partition/extension NALs. Non-IDR intra pictures leave closed GOP unverified, not automatically invalid. This is a conservative syntax-level finding for conforming streams, not proof of decodability or platform acceptance. HEVC remains unverified in this version.

The process is capped at15seconds and8MiB diagnostic output, kills and waits on timeout/output overflow, never prints source diagnostics in the UI. Missing FFmpeg, malformed video or unsupported features return unverified while retaining the basic probe. Keyframe flags alone are not proof. The existing50MiB input ceiling remains in place to avoid unbounded memory use; larger files still need a streaming probe design, not a silent ceiling increase.

VBR remains unverified. HRD CBR flags are raw evidence only. Neither absent HRD nor cbr_flag=0 nor packet-size variation establishes the encoder's actual rate-control mode. No automatic conversion or upload follows a measurement.

Sources checked:
- https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/ : closed GOP and VBR requirements.
- https://ffmpeg.org/ffmpeg-bitstream-filters.html : trace_headers scope and supported codecs.
- https://ffmpeg.org/ffprobe.html : stream/packet/frame and read-interval semantics.
- https://www.rfc-editor.org/rfc/rfc6184.html : IDR refresh semantics.
- https://www.wireshark.org/docs/dfref/h/h264.html : H.264 header fields.
- https://developer.ridgerun.com/wiki/index.php/Inspecting_H.264_Headers : header structure examples.
- https://basisvideo.com/video-encoding/free-h-264-test-streams-ffmpeg-recipes-gop-bitrate : isolated open/closed GOP and rate-control fixture recipes.

Tests use generated H.264 open and closed GOP files, missing-tool fallback, output/time limits, unsupported types and HRD flags that never grant a rate-control pass.
