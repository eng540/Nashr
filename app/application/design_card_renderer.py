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

from PIL import Image, ImageDraw, ImageFont, features


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

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CardRenderConfig":
        allowed = {"width", "height", "padding", "background", "foreground", "font_size", "line_spacing", "max_lines", "font_family", "show_title", "show_source_attribution", "title_font_size", "attribution_font_size", "text_alignment"}
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
        for color in (config.background, config.foreground):
            if not isinstance(color, str) or len(color) not in {4, 7} or not color.startswith("#"):
                raise ValueError("Card colors must be hex color values.")
            try:
                int(color[1:], 16)
            except ValueError as exc:
                raise ValueError("Card colors must be hex color values.") from exc
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


def render_arabic_text_card_png(
    approved_text: str,
    configuration: Mapping[str, Any] | None = None,
    *,
    title: str | None = None,
    attribution: str | None = None,
    font_path: str | None = None,
) -> bytes:
    """Render approved text deterministically; never call a generative model."""
    if not isinstance(approved_text, str) or not approved_text.strip():
        raise ValueError("A non-empty approved text Artifact is required.")
    if not features.check("raqm"):
        raise RuntimeError("Arabic card rendering requires Pillow built with libraqm support.")
    config = CardRenderConfig.from_mapping(configuration or {})
    environment_key = {
        "default": "NASHR_CARD_FONT_PATH",
        "naskh": "NASHR_CARD_FONT_NASKH_PATH",
        "sans": "NASHR_CARD_FONT_SANS_PATH",
    }[config.font_family]
    selected_font = font_path or os.environ.get(environment_key)
    if not selected_font and config.font_family == "default":
        selected_font = os.environ.get("NASHR_CARD_FONT_PATH")
    if not selected_font:
        candidates_by_family = {
            "default": (
                "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
                "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            ),
            "naskh": (
                "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSerif.ttf",
            ),
            "sans": (
                "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
            ),
        }
        selected_font = next(
            (candidate for candidate in candidates_by_family[config.font_family] if Path(candidate).is_file()),
            None,
        )
    if not selected_font or not Path(selected_font).is_file():
        raise RuntimeError(f"Set {environment_key} to an installed, licensed Arabic-capable font file.")
    try:
        font = ImageFont.truetype(selected_font, config.font_size, layout_engine=ImageFont.Layout.RAQM)
    except (OSError, ValueError) as exc:
        raise RuntimeError("The configured card font could not be loaded with Arabic text layout support.") from exc

    image = Image.new("RGB", (config.width, config.height), config.background)
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
