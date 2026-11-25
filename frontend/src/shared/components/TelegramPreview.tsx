import {useMemo,type ReactNode} from "react";
const TELEGRAM_HTML_TAGS = new Set(["b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "pre", "a", "blockquote", "span", "br"]);

function isTelegramMarkupValid(content: string): boolean {
  const tagPattern = /<\/?([a-zA-Z][\w-]*)([^>]*)>/g;
  const tags = Array.from(content.matchAll(tagPattern));
  const hasRichTag = tags.some((match) => TELEGRAM_HTML_TAGS.has(match[1].toLowerCase()));
  if (!hasRichTag) return true;
  const stack: string[] = [];
  for (const match of tags) {
    const tag = match[1].toLowerCase();
    const closing = match[0].startsWith("</");
    const selfClosing = /\/>$/.test(match[0]) || tag === "br";
    if (!TELEGRAM_HTML_TAGS.has(tag)) return false;
    if (closing) {
      if (stack.pop() !== tag) return false;
    } else if (!selfClosing) {
      stack.push(tag);
    }
  }
  return stack.length === 0;
}

function renderTelegramNode(node: Node, key: string): ReactNode {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent;
  if (!(node instanceof HTMLElement)) return null;
  const tag = node.tagName.toLowerCase();
  const children = Array.from(node.childNodes).map((child, index) => renderTelegramNode(child, `${key}-${index}`));
  switch (tag) {
    case "b": case "strong": return <strong key={key}>{children}</strong>;
    case "i": case "em": return <em key={key}>{children}</em>;
    case "u": case "ins": return <u key={key}>{children}</u>;
    case "s": case "strike": case "del": return <del key={key}>{children}</del>;
    case "code": return <code key={key} className="rounded bg-slate-100 px-1">{children}</code>;
    case "pre": return <pre key={key} className="overflow-x-auto rounded-lg bg-slate-100 p-3 text-left" dir="ltr">{children}</pre>;
    case "blockquote": return <blockquote key={key} className="my-2 border-r-4 border-slate-300 pr-3 text-slate-600">{children}</blockquote>;
    case "br": return <br key={key} />;
    case "span": return node.classList.contains("tg-spoiler") ? <span key={key} className="rounded bg-slate-800 text-slate-800 hover:text-white">{children}</span> : <span key={key}>{children}</span>;
    case "a": {
      const href = node.getAttribute("href") ?? "";
      if (!/^(https?:\/\/|tg:\/\/)/i.test(href)) return <span key={key}>{children}</span>;
      return <a key={key} href={href} target="_blank" rel="noreferrer" className="text-indigo-700 underline">{children}</a>;
    }
    default: return <span key={key}>{children}</span>;
  }
}

export function TelegramPreview({ content, onClose }: { content: string; onClose?: () => void }) {
  const valid = isTelegramMarkupValid(content);
  const nodes = useMemo(() => {
    if (!valid) return null;
    const doc = new DOMParser().parseFromString(content, "text/html");
    const hasRichTag = Array.from(doc.body.querySelectorAll("*")).some((element) => TELEGRAM_HTML_TAGS.has(element.tagName.toLowerCase()));
    if (!hasRichTag) return content;
    return Array.from(doc.body.childNodes).map((node, index) => renderTelegramNode(node, `telegram-preview-${index}`));
  }, [content, valid]);
  return <section className="mt-4 rounded-xl border bg-slate-50 p-4" aria-label="معاينة تيليجرام">
    <div className="mb-2 flex items-center justify-between gap-2"><h4 className="text-sm font-bold">معاينة تيليجرام</h4>{onClose ? <button type="button" onClick={onClose} className="rounded-lg border bg-white px-3 py-1 text-sm">إغلاق المعاينة</button> : <span className="text-xs text-slate-500">عرض تقني للتنسيق قبل الاعتماد</span>}</div>
    {!valid
      ? <p role="alert" className="text-sm text-rose-700">وسوم HTML غير متوازنة أو غير مدعومة. لن يقبل محول تيليجرام هذا التنسيق.</p>
      : <div dir="auto" className="whitespace-pre-wrap break-words rounded-lg bg-white p-4 text-sm leading-7 text-slate-800">{nodes}</div>}
  </section>;
}
