"""Deterministic PNG rendering for human-approved Arabic text Artifacts.

No generative model is used to typeset Arabic. The renderer fails closed when a
configured Arabic-capable font or Pillow's RAQM text layout engine is unavailable.
"""
from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageDraw, ImageFont, ImageOps, features


@dataclass(frozen=True)
class CardRenderConfig:
    width: int = 1080
    height: int = 1350
    padding: int = 88
    background: str = "#F7F2E8"
    foreground: str = "#24211D"
    font_size: int = 42
    line_spacing: int = 18
    max_lines: int = 22
    font_family: str = "default"
    show_title: bool = True
    show_source_attribution: bool = False
    title_font_size: int = 34
    attribution_font_size: int = 22
    text_alignment: str = "right"
    background_overlay_color: str = "#F7F2E8"
    background_overlay_opacity: int = 225

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CardRenderConfig":
        allowed = {"width", "height", "padding", "background", "foreground", "font_size", "line_spacing", "max_lines", "font_family", "show_title", "show_source_attribution", "title_font_size", "attribution_font_size", "text_alignment", "background_overlay_color", "background_overlay_opacity"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError("Unsupported card render configuration: " + ", ".join(sorted(unknown)))
        try:
            config = cls(**value)
        except TypeError as exc:
            raise ValueError("Card render configuration contains invalid field types.") from exc
        if not (320 <= config.width <= 2400 and 320 <= config.height <= 3200):
            raise ValueError("Card dimensions must be within the supported bounds.")
        if not (16 <= config.padding < min(config.width, config.height) // 3):
            raise ValueError("Card padding is outside the supported bounds.")
        if not (16 <= config.font_size <= 120 and 0 <= config.line_spacing <= 80):
            raise ValueError("Card typography settings are outside the supported bounds.")
        if not (1 <= config.max_lines <= 100):
            raise ValueError("Card max_lines must be between 1 and 100.")
        if not isinstance(config.font_family, str) or config.font_family not in {"default", "naskh", "sans"}:
            raise ValueError("Card font_family must be default, naskh, or sans.")
        if not isinstance(config.show_title, bool) or not isinstance(config.show_source_attribution, bool):
            raise ValueError("Card title and source-attribution toggles must be booleans.")
        if any(isinstance(size, bool) or not isinstance(size, int) or not 12 <= size <= 100 for size in (config.title_font_size, config.attribution_font_size)):
            raise ValueError("Card title and attribution font sizes must be between 12 and 100.")
        if not isinstance(config.text_alignment, str) or config.text_alignment not in {"right", "center"}:
            raise ValueError("Card text_alignment must be right or center.")
        for color in (config.background, config.foreground, config.background_overlay_color):
            if not isinstance(color, str) or len(color) not in {4, 7} or not color.startswith("#"):
                raise ValueError("Card colors must be hex color values.")
            try:
                int(color[1:], 16)
            except ValueError as exc:
                raise ValueError("Card colors must be hex color values.") from exc
        if isinstance(config.background_overlay_opacity, bool) or not isinstance(config.background_overlay_opacity, int) or not 0 <= config.background_overlay_opacity <= 255:
            raise ValueError("background_overlay_opacity must be an integer between 0 and 255.")
        return config


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text or " ", font=font, direction="rtl", language="ar")
    return bbox[2] - bbox[0]


def _wrap_paragraph(draw: ImageDraw.ImageDraw, paragraph: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    if not paragraph:
        return [""]
    tokens = re.findall(r"\s+|\S+", paragraph)
    lines: list[str] = []
    current = ""
    for token in tokens:
        candidate = current + token
        if _text_width(draw, candidate, font) <= max_width:
            current = candidate
            continue
        if token.isspace():
            # Preserve every source character; if a whitespace run itself
            # overflows, keep it with the current line rather than deleting it.
            if current:
                lines.append(current)
            current = token
            continue
        if current and current.strip():
            lines.append(current)
            current = token
        elif current:
            lines.append(current)
            current = token
        else:
            current = token
        if _text_width(draw, current, font) > max_width:
            raise ValueError("A word cannot fit within the configured card width at this font size.")
    if current or not lines:
        lines.append(current)
    return lines


def resolve_card_font_path(font_family: str = "default", font_path: str | None = None) -> str:
    """Resolve a deterministic, licensed Arabic-capable font for this renderer.

    The packaged Noto Naskh Arabic font is the production-safe default. An
    explicit path or family-specific environment variable takes precedence,
    but an invalid explicit choice fails closed instead of silently changing
    typography.
    """
    if font_family not in {"default", "naskh", "sans"}:
        raise ValueError("font_family must be default, naskh, or sans.")
    environment_key = {
        "default": "NASHR_CARD_FONT_PATH",
        "naskh": "NASHR_CARD_FONT_NASKH_PATH",
        "sans": "NASHR_CARD_FONT_SANS_PATH",
    }[font_family]
    selected_font = font_path or os.environ.get(environment_key)
    if selected_font:
        if not Path(selected_font).is_file():
            raise RuntimeError(f"The configured card font at {environment_key} is not an installed font file.")
        return str(Path(selected_font).resolve())

    packaged_naskh = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "NotoNaskhArabic[wght].ttf"
    candidates_by_family = {
        "default": (
            packaged_naskh,
            Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"),
            Path("/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
        ),
        "naskh": (
            packaged_naskh,
            Path("/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf"),
            Path("/usr/share/fonts/truetype/freefont/FreeSerif.ttf"),
        ),
        "sans": (
            Path("/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
        ),
    }
    selected = next((candidate for candidate in candidates_by_family[font_family] if candidate.is_file()), None)
    if selected is None:
        raise RuntimeError(f"Set {environment_key} to an installed, licensed Arabic-capable font file.")
    return str(selected.resolve())


def validate_background_image_bytes(background_image: bytes) -> None:
    """Validate provider output before composing any approved text over it."""
    try:
        with Image.open(io.BytesIO(background_image)) as source:
            if source.format not in {"PNG", "JPEG", "WEBP"}:
                raise ValueError("AI background format must be PNG, JPEG, or WEBP.")
            source.verify()
    except (OSError, ValueError) as exc:
        raise ValueError("AI background is not a valid supported image.") from exc


def render_arabic_text_card_png(
    approved_text: str,
    configuration: Mapping[str, Any] | None = None,
    *,
    title: str | None = None,
    attribution: str | None = None,
    font_path: str | None = None,
    background_image: bytes | None = None,
) -> bytes:
    """Render approved text deterministically; never call a generative model."""
    if not isinstance(approved_text, str) or not approved_text.strip():
        raise ValueError("A non-empty approved text Artifact is required.")
    if not features.check("raqm"):
        raise RuntimeError("Arabic card rendering requires Pillow built with libraqm support.")
    config = CardRenderConfig.from_mapping(configuration or {})
    selected_font = resolve_card_font_path(config.font_family, font_path)
    try:
        font = ImageFont.truetype(selected_font, config.font_size, layout_engine=ImageFont.Layout.RAQM)
    except (OSError, ValueError) as exc:
        raise RuntimeError("The configured card font could not be loaded with Arabic text layout support.") from exc

    if background_image is None:
        image = Image.new("RGB", (config.width, config.height), config.background)
    else:
        try:
            with Image.open(io.BytesIO(background_image)) as source_background:
                image = ImageOps.fit(
                    source_background.convert("RGB"),
                    (config.width, config.height),
                    method=Image.Resampling.LANCZOS,
                )
        except (OSError, ValueError) as exc:
            raise ValueError("AI background is not a valid supported image.") from exc
        if config.background_overlay_opacity:
            overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_color = tuple(
                int(config.background_overlay_color[index:index + 2], 16)
                for index in (1, 3, 5)
            ) + (config.background_overlay_opacity,)
            margin = min(config.padding, min(config.width, config.height) // 3)
            overlay_draw.rounded_rectangle(
                (margin, margin, config.width - margin, config.height - margin),
                radius=min(32, margin),
                fill=overlay_color,
            )
            image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(image)
    max_width = config.width - (2 * config.padding)
    title_font = ImageFont.truetype(selected_font, config.title_font_size, layout_engine=ImageFont.Layout.RAQM)
    attribution_font = ImageFont.truetype(selected_font, config.attribution_font_size, layout_engine=ImageFont.Layout.RAQM)

    title_lines: list[str] = []
    if config.show_title and isinstance(title, str) and title.strip():
        title_lines = _wrap_paragraph(draw, title.strip(), title_font, max_width)
        if len(title_lines) > 3:
            raise ValueError("Card title exceeds three lines; shorten the title or increase the canvas.")
    attribution_lines: list[str] = []
    if config.show_source_attribution and isinstance(attribution, str) and attribution.strip():
        attribution_lines = _wrap_paragraph(draw, attribution.strip(), attribution_font, max_width)
        if len(attribution_lines) > 2:
            raise ValueError("Source attribution exceeds two lines; shorten the attribution or increase the canvas.")

    lines: list[str] = []
    for paragraph in approved_text.splitlines():
        lines.extend(_wrap_paragraph(draw, paragraph, font, max_width))
    if len(lines) > config.max_lines:
        raise ValueError(
            f"Approved text needs {len(lines)} lines but the configured card allows {config.max_lines}; "
            "increase the card size, reduce font size, or split the content explicitly."
        )

    def heights_for(values: list[str], selected_font: ImageFont.FreeTypeFont) -> list[int]:
        heights = []
        for value in values:
            bbox = draw.textbbox((0, 0), value or " ", font=selected_font, direction="rtl", language="ar")
            heights.append(max(1, bbox[3] - bbox[1]))
        return heights

    title_heights = heights_for(title_lines, title_font)
    body_heights = heights_for(lines, font)
    attribution_heights = heights_for(attribution_lines, attribution_font)
    title_total = sum(title_heights) + max(0, len(title_lines) - 1) * config.line_spacing
    attribution_total = sum(attribution_heights) + max(0, len(attribution_lines) - 1) * config.line_spacing
    top = config.padding
    if title_lines:
        for line, line_height in zip(title_lines, title_heights):
            draw.text((config.width - config.padding, top), line, fill=config.foreground, font=title_font, anchor="ra", direction="rtl", language="ar")
            top += line_height + config.line_spacing
        top += config.line_spacing
    bottom = config.height - config.padding
    if attribution_lines:
        bottom -= attribution_total
        y_attribution = bottom
        for line, line_height in zip(attribution_lines, attribution_heights):
            draw.text((config.width - config.padding, y_attribution), line, fill=config.foreground, font=attribution_font, anchor="ra", direction="rtl", language="ar")
            y_attribution += line_height + config.line_spacing
        bottom -= config.line_spacing
    body_total = sum(body_heights) + max(0, len(lines) - 1) * config.line_spacing
    if top + body_total > bottom:
        raise ValueError("Approved text, title, and attribution do not fit vertically; no text was truncated.")
    y = top + max(0, (bottom - top - body_total) // 2)
    body_x = config.width - config.padding if config.text_alignment == "right" else config.width // 2
    body_anchor = "ra" if config.text_alignment == "right" else "ma"
    for line, line_height in zip(lines, body_heights):
        draw.text((body_x, y), line, fill=config.foreground, font=font, anchor=body_anchor, direction="rtl", language="ar")
        y += line_height + config.line_spacing

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
