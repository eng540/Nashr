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

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CardRenderConfig":
        allowed = {"width", "height", "padding", "background", "foreground", "font_size", "line_spacing", "max_lines", "font_family"}
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
    lines: list[str] = []
    for paragraph in approved_text.splitlines():
        lines.extend(_wrap_paragraph(draw, paragraph, font, max_width))
    if len(lines) > config.max_lines:
        raise ValueError(
            f"Approved text needs {len(lines)} lines but the configured card allows {config.max_lines}; "
            "increase the card size, reduce font size, or split the content explicitly."
        )

    line_heights = [
        max(1, draw.textbbox((0, 0), line or " ", font=font, direction="rtl", language="ar")[3]
            - draw.textbbox((0, 0), line or " ", font=font, direction="rtl", language="ar")[1])
        for line in lines
    ]
    total_height = sum(line_heights) + max(0, len(lines) - 1) * config.line_spacing
    y = (config.height - total_height) // 2
    if y < config.padding or y + total_height > config.height - config.padding:
        raise ValueError("Approved text does not fit vertically; no text was truncated.")

    for line, line_height in zip(lines, line_heights):
        draw.text(
            (config.width - config.padding, y),
            line,
            fill=config.foreground,
            font=font,
            anchor="ra",
            direction="rtl",
            language="ar",
        )
        y += line_height + config.line_spacing

    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
