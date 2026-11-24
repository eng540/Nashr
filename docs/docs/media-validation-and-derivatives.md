# Media checks and explicit JPEG preview

2026-11-24. Preparation only, no execution permission.

The original-file probe now traverses bounded ISO BMFF boxes and checks moov before mdat, nested edit lists, and declared AAC bit rate. Malformed containers fail inspection. Closed GOP and variable bitrate are still unverified, as are platform acceptance and accounts. The read ceiling remains 50 MiB, not Instagram's 300 MB upload allowance.

Telegram photo measurements now flag byte size above 10 MB, width plus height above 10000, and aspect ratio above 20. Video measurements flag 50 MB. These conservative decimal limits are inspection findings only and do not replace the existing final upload validator or change old schedule contracts.

An explicit Instagram JPEG preview is available for approved stored images with prepared, current platform copies. The operator chooses a black or white background before conversion. Input is bounded to 50 MiB / 40 million pixels. Animated, multipage, invalid-profile and unprofiled-CMYK images are refused. The complete oriented frame must already satisfy 4:5 through 1.91:1. There is no crop, AI generation, text change, or automatic quality reduction. Width is normalized to 320–1440, quality 90, sRGB output, EXIF/GPS removed. Missing source ICC means an explicitly disclosed sRGB assumption. Output above 8 MB is refused.

The JPEG is returned transiently with a download link, source fingerprint, copy version, source/output hashes and measurements. Responses are no-store. Source and copy are rechecked after processing. No storage upload, database row, approval, schedule, publication or source replacement happens. It is a review/download aid, not a persistent execution asset. A durable per-platform asset lifecycle and video conversion require a separate design with stale/version review and explicit selection before execution. This change does not claim those are complete.

## Sources checked

- https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/media/ , JPEG, sRGB, 8 MB, width and ratio; MOV/MP4, no edit lists, front moov, codecs, bitrates.
- https://core.telegram.org/bots/api/methods/sendphoto.md , 10 MB, sum of dimensions, ratio.
- https://core.telegram.org/bots/api/methods/sendvideo.md , 50 MB and MPEG4 client support.

## Verification

Real PNG/JPEG transparency, ICC, EXIF orientation and metadata removal; up/downscale; invalid ratio/profile and animation rejection; real ffmpeg-generated MP4; nested edit-list and malformed box fixtures; read-only API checks with storage writes forbidden; stale copy checks; UI choice, download, invalidation and mobile/desktop screenshots. No live social sends needed.
