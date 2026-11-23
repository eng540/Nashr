import html
import os
import re
from html.parser import HTMLParser

import httpx

from app.domain.publications import IPublisher, PublishResult
from app.domain.quizzes import QuizPayload


_ALLOWED_TAGS = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "code", "pre", "a", "blockquote", "span", "br",
}
_VOID_TAGS = {"br"}
_ALLOWED_ENTITIES = {"lt", "gt", "amp", "quot"}
_RICH_TAG_RE = re.compile(
    r"</?(?:b|strong|i|em|u|ins|s|strike|del|code|pre|a|blockquote|span|br)(?:\s|/?>)",
    re.IGNORECASE,
)


class _TelegramHTMLSerializer(HTMLParser):
    """Validate and safely serialize the subset of HTML supported by Telegram."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.output: list[str] = []
        self.stack: list[str] = []
        self.visible_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag not in _ALLOWED_TAGS:
            raise ValueError(f"Unsupported Telegram HTML tag: <{tag}>")
        if tag == "br":
            if attrs:
                raise ValueError("Telegram line breaks do not accept attributes.")
            self.output.append("\n")
            self.visible_text.append("\n")
            return
        normalized: list[tuple[str, str]] = []
        for name, value in attrs:
            name = name.lower()
            if tag == "a" and name == "href" and value is not None:
                if not value.strip().lower().startswith(("https://", "http://", "tg://")):
                    raise ValueError("Telegram links must use http, https, or tg URLs.")
                normalized.append(("href", value))
            elif tag == "span" and name == "class" and value == "tg-spoiler":
                normalized.append(("class", value))
            else:
                raise ValueError(f"Unsupported attribute {name!r} on Telegram <{tag}>.")
        if tag == "a" and not any(name == "href" for name, _ in normalized):
            raise ValueError("Telegram <a> tags require an href attribute.")
        attrs_text = "".join(f' {name}="{html.escape(value, quote=True)}"' for name, value in normalized)
        self.output.append(f"<{tag}{attrs_text}>")
        if tag not in _VOID_TAGS:
            self.stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _VOID_TAGS or not self.stack or self.stack[-1] != tag:
            raise ValueError(f"Unbalanced Telegram HTML closing tag: </{tag}>")
        self.stack.pop()
        self.output.append(f"</{tag}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "br" or attrs:
            raise ValueError("Only <br/> is supported as a self-closing Telegram tag.")
        self.output.append("\n")
        self.visible_text.append("\n")

    def handle_data(self, data: str) -> None:
        self.output.append(html.escape(data, quote=False))
        self.visible_text.append(data)

    def handle_entityref(self, name: str) -> None:
        if name not in _ALLOWED_ENTITIES:
            raise ValueError(f"Unsupported HTML entity: &{name};")
        self.output.append(f"&{name};")
        self.visible_text.append({"lt": "<", "gt": ">", "amp": "&", "quot": '"'}[name])

    def handle_charref(self, name: str) -> None:
        try:
            value = chr(int(name[1:], 16)) if name.lower().startswith("x") else chr(int(name))
        except (ValueError, OverflowError):
            raise ValueError(f"Invalid HTML character reference: &#{name};") from None
        self.output.append(f"&#{name};")
        self.visible_text.append(value)

    def handle_comment(self, data: str) -> None:
        raise ValueError("HTML comments are not supported in Telegram messages.")

    def handle_decl(self, decl: str) -> None:
        raise ValueError("HTML declarations are not supported in Telegram messages.")


def telegram_html_content(content: str, *, max_visible_characters: int = 4096) -> str:
    """Prepare plain text or rich Telegram HTML and enforce structural/platform limits.

    Plain text is escaped before Telegram's HTML parser sees it. Rich HTML is
    validated against Telegram's supported subset, escaped safely, and checked
    for balanced tags. This is technical validation, not editorial evaluation.
    """
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Telegram message content cannot be empty.")

    if not _RICH_TAG_RE.search(content):
        prepared = html.escape(content, quote=False)
        visible_text = content
    else:
        parser = _TelegramHTMLSerializer()
        try:
            parser.feed(content)
            parser.close()
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("Telegram HTML could not be parsed.") from exc
        if parser.stack:
            raise ValueError("Telegram HTML contains unclosed tags.")
        prepared = "".join(parser.output)
        visible_text = "".join(parser.visible_text)

    if len(visible_text) > max_visible_characters:
        raise ValueError(f"Telegram messages cannot exceed {max_visible_characters} visible characters.")
    return prepared


def telegram_html_to_visible_text(content: str) -> str:
    """Return the visible text from the exact Telegram HTML subset accepted by the publisher.

    This is the shared content interpretation for non-Telegram renderers: tags
    never leak into an image, supported entities are decoded, and explicit
    Telegram line breaks remain line breaks. The publisher still sends the
    original validated rich HTML so Telegram retains its native formatting.
    """
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Telegram message content cannot be empty.")
    # Route any HTML-like tag through the same validator, including unsupported tags.
    # Otherwise an unsupported tag such as <div> could be mistaken for ordinary text.
    if not re.search(r"</?[A-Za-z][^>]*>", content):
        return content
    parser = _TelegramHTMLSerializer()
    try:
        parser.feed(content)
        parser.close()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Telegram HTML could not be parsed.") from exc
    if parser.stack:
        raise ValueError("Telegram HTML contains unclosed tags.")
    return "".join(parser.visible_text)


class TelegramPublisher(IPublisher):
    """Publish Telegram messages through the Bot API using safe rich-text HTML."""

    def __init__(self, token: str | None = None, timeout: float = 30.0) -> None:
        """Initialize the Telegram Bot API client."""
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.timeout = timeout
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required.")

    async def publish(
        self,
        *,
        destination: str,
        content: str,
        media: bytes | None = None,
        media_mime_type: str | None = None,
        quiz: QuizPayload | None = None,
        media_kind: str | None = None,
        media_filename: str | None = None,
        native: dict | None = None,
        album: list[dict] | None = None,
        live_photo: dict | None = None,
    ) -> PublishResult:
        """Send text, an approved visual card, or a native Telegram quiz poll."""
        if quiz is not None and media is not None:
            raise ValueError("A Telegram quiz cannot be combined with image media.")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            if live_photo is not None:
                if any(value is not None for value in (album, native, quiz, media)):
                    raise ValueError('Live Photo cannot be combined with other content.')
                from app.domain.telegram_live_photo import validate_live_motion
                from app.domain.telegram_media import media_request
                validate_live_motion(live_photo['motion'])
                _, _, photo_name = media_request('IMAGE', live_photo['photo_mime'], live_photo['photo'])
                response = await client.post(f'https://api.telegram.org/bot{self.token}/sendLivePhoto',
                    data={'chat_id': destination, 'caption': telegram_html_content(content, max_visible_characters=1024), 'parse_mode': 'HTML'},
                    files={'photo': (photo_name, live_photo['photo'], live_photo['photo_mime']), 'live_photo': ('motion.mp4', live_photo['motion'], 'video/mp4')})
            elif album is not None:
                if native is not None or quiz is not None or media is not None:
                    raise ValueError("An album cannot be combined with other content.")
                from app.domain.telegram_albums import validate_album_group
                from app.domain.telegram_media import media_request
                import json
                validate_album_group([item["kind"] for item in album])
                entries, files = [], {}
                for index, item in enumerate(album):
                    _, _, filename = media_request(item["kind"], item["mime_type"], item["data"], item.get("filename"))
                    key = "media" + str(index)
                    files[key] = (filename, item["data"], item["mime_type"])
                    entry = {"type": {"IMAGE": "photo", "VIDEO": "video", "AUDIO": "audio", "DOCUMENT": "document"}[item["kind"]], "media": "attach://" + key}
                    if item.get("caption"):
                        entry.update(caption=telegram_html_content(item["caption"], max_visible_characters=1024), parse_mode="HTML")
                    entries.append(entry)
                response = await client.post(f"https://api.telegram.org/bot{self.token}/sendMediaGroup",
                    data={"chat_id": destination, "media": json.dumps(entries)}, files=files)
            elif native is not None:
                if quiz is not None or media is not None:
                    raise ValueError("Native content cannot be combined with quiz or media.")
                from app.domain.telegram_payloads import native_payload
                method, data = native_payload(native)
                response = await client.post(f"https://api.telegram.org/bot{self.token}/{method}", json={"chat_id": destination, **data})
            elif quiz is not None:
                url = f"https://api.telegram.org/bot{self.token}/sendPoll"
                response = await client.post(url, json=quiz.to_telegram_payload(destination))
            elif media is None:
                url = f"https://api.telegram.org/bot{self.token}/sendMessage"
                message = telegram_html_content(content)
                response = await client.post(
                    url,
                    json={
                        "chat_id": destination,
                        "text": message,
                        "parse_mode": "HTML",
                    },
                )
            else:
                from app.domain.telegram_media import media_request, NO_CAPTION
                selected_kind = media_kind or ("IMAGE" if (media_mime_type or "").startswith("image/") else "VIDEO")
                method, field, filename = media_request(selected_kind, media_mime_type, media, media_filename)
                url = f"https://api.telegram.org/bot{self.token}/{method}"
                data = {"chat_id": destination}
                if selected_kind not in NO_CAPTION:
                    data.update({"caption": telegram_html_content(content, max_visible_characters=1024), "parse_mode": "HTML"})
                response = await client.post(url, data=data, files={field: (filename, media, media_mime_type)})
            response.raise_for_status()
            payload = response.json()
        if album is not None:
            results = payload.get("result")
            if not payload.get("ok") or not isinstance(results, list) or len(results) != len(album) or any(not isinstance(x, dict) or not x.get("message_id") for x in results):
                raise RuntimeError("Telegram returned an ambiguous album response; do not retry automatically.")
            ids = tuple(str(item["message_id"]) for item in results)
            return PublishResult(external_id=ids[0], external_ids=ids)
        if not payload.get("ok") or "result" not in payload or "message_id" not in payload["result"]:
            raise RuntimeError("Telegram returned an invalid publish response.")
        return PublishResult(external_id=str(payload["result"]["message_id"]))

    async def update_live_location(self, *, destination, message_id, action, payload):
        if action not in {'UPDATE', 'STOP'}:
            raise ValueError('Unsupported live location action.')
        if action == 'UPDATE':
            from app.domain.telegram_payloads import native_payload
            _, data = native_payload({'type': 'LOCATION', **payload})
            method = 'editMessageLiveLocation'
        else:
            if payload:
                raise ValueError('Stop does not accept coordinates.')
            method, data = 'stopMessageLiveLocation', {}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f'https://api.telegram.org/bot{self.token}/{method}', json={'chat_id': destination, 'message_id': int(message_id), **data})
            response.raise_for_status()
            result = response.json()
        message = result.get('result')
        if not result.get('ok') or not isinstance(message, dict) or str(message.get('message_id')) != str(message_id):
            raise RuntimeError('Live location update result is uncertain; do not retry automatically.')
        return message
