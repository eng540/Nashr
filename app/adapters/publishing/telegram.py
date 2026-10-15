import html
import os
import re
from html.parser import HTMLParser

import httpx

from app.domain.publications import IPublisher, PublishResult


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
        self.output.append("<br>")

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


def telegram_html_content(content: str) -> str:
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

    if len(visible_text) > 4096:
        raise ValueError("Telegram messages cannot exceed 4096 visible characters.")
    return prepared


class TelegramPublisher(IPublisher):
    """Publish Telegram messages through the Bot API using safe rich-text HTML."""

    def __init__(self, token: str | None = None, timeout: float = 30.0) -> None:
        """Initialize the Telegram Bot API client."""
        self.token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.timeout = timeout
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required.")

    async def publish(self, *, destination: str, content: str) -> PublishResult:
        """Send a message to Telegram and return its message identifier."""
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        message = telegram_html_content(content)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                url,
                json={
                    "chat_id": destination,
                    "text": message,
                    "parse_mode": "HTML",
                },
            )
            response.raise_for_status()
            payload = response.json()
        if not payload.get("ok") or "result" not in payload or "message_id" not in payload["result"]:
            raise RuntimeError("Telegram returned an invalid publish response.")
        return PublishResult(external_id=str(payload["result"]["message_id"]))
