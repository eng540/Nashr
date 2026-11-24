"""Deployment preflight for the deterministic Arabic card renderer."""

from PIL import Image, ImageDraw, ImageFont, features, ImageCms
import io

from app.application.design_card_renderer import resolve_card_font_path


def main() -> None:
    if not features.check("raqm"):
        raise SystemExit(
            "Arabic card renderer preflight failed: Pillow has no RAQM support. "
            "Build Pillow from source with libraqm, HarfBuzz and FriBidi installed."
        )

    if not features.check("littlecms2"):
        print("WARNING: JPEG previews unavailable: Pillow lacks littlecms2. Existing publishing remains available.")
        return _arabic_preflight()
    try:
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        preview = io.BytesIO()
        Image.new("RGB",(4,4),"white").save(preview,format="JPEG",icc_profile=profile)
        with Image.open(io.BytesIO(preview.getvalue())) as decoded:
            if not decoded.info.get("icc_profile"):
                raise ValueError("JPEG ICC profile was not preserved.")
    except Exception as exc:
        print(f"WARNING: JPEG color preflight failed: {type(exc).__name__}. Existing publishing remains available.")
    _arabic_preflight()


def _arabic_preflight():
    try:
        font_path = resolve_card_font_path("naskh")
        font = ImageFont.truetype(font_path, 32, layout_engine=ImageFont.Layout.RAQM)
        image = Image.new("RGB", (640, 160), "white")
        draw = ImageDraw.Draw(image)
        draw.text((620, 20), "إنَّ الربيع هو الشباب الثاني", font=font, fill="black", direction="rtl", language="ar")
        draw.textbbox((0, 0), "فائدة أدبية: إنَّ الربيع هو الشباب الثاني", font=font, direction="rtl", language="ar")
    except Exception as exc:
        raise SystemExit(f"Arabic card renderer preflight failed: {exc}") from exc

    print(f"Arabic card renderer preflight passed (RAQM enabled; font={font_path}).")


if __name__ == "__main__":
    main()
