"""Bounded, authenticated import of Engineering540 source archives.

Reuses the CLI importer. Archives contain only selected topics/designs and a
matching designs/index.csv. No archive scripts are ever executed.
"""
from __future__ import annotations

import io
import os
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database.session import engine
from app.application.engineering540_import import import_designs, import_topics

router = APIRouter(tags=["library-import"])
MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_EXPANDED_BYTES = 50 * 1024 * 1024
MAX_FILES = 102
MAX_ITEM_BYTES = 10 * 1024 * 1024
LOCK_ID = 5401051


def validate_archive(data: bytes) -> list[tuple[str, bytes]]:
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive exceeds 25 MiB.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("A valid ZIP archive is required.") from exc
    with archive:
        members = archive.infolist()
        if not members or len(members) > MAX_FILES:
            raise ValueError("Archive must contain 1 to 102 entries.")
        if sum(m.filename.endswith((".md", ".webp")) for m in members) > 100:
            raise ValueError("At most 100 content items per archive.")
        total = 0
        seen = set()
        result = []
        for member in members:
            name = member.filename
            path = PurePosixPath(name)
            if (path.is_absolute() or "\\" in name or any(p in {"..", ".", ""} for p in name.split("/"))
                    or name in seen or stat.S_ISLNK(member.external_attr >> 16) or member.flag_bits & 1):
                raise ValueError("Unsafe, encrypted or duplicate ZIP entry.")
            seen.add(name)
            allowed = (len(path.parts) == 3 and path.parts[0] == "content"
                       and path.parts[1].startswith("P") and path.name.startswith("P") and path.suffix == ".md")
            allowed = allowed or name == "designs/index.csv" or (
                len(path.parts) == 3 and path.parts[0] == "designs"
                and path.parts[1].startswith("batch-") and path.name.startswith("d") and path.suffix == ".webp")
            if not allowed or member.is_dir():
                raise ValueError("Only topic Markdown, design WebP and designs/index.csv are accepted.")
            total += member.file_size
            if member.file_size > MAX_ITEM_BYTES or total > MAX_EXPANDED_BYTES:
                raise ValueError("Expanded archive exceeds its size limit.")
            if member.file_size > max(1024 * 1024, member.compress_size * 200):
                raise ValueError("Suspicious ZIP compression ratio.")
            payload = archive.read(member)
            if len(payload) != member.file_size:
                raise ValueError("Invalid ZIP entry size.")
            result.append((name, payload))
        # Validate the CSV's paths independently: it must not reference outside
        # this archive or turn the importer into a local filesystem reader.
        import csv
        rows = []
        for name, payload in result:
            if name == "designs/index.csv":
                rows = list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))
        if len(rows) > 100:
            raise ValueError("At most 100 designs per archive.")
        for row in rows:
            referenced = (row.get("الملف") or "").strip()
            if referenced not in seen or not referenced.startswith("designs/") or not referenced.endswith(".webp"):
                raise ValueError("Every design index path must reference a WebP inside this archive.")
        webp_names = {name for name in seen if name.endswith(".webp")}
        if webp_names != {(row.get("الملف") or "").strip() for row in rows}:
            raise ValueError("Design index and archive files must match exactly.")
        return result


@router.post("/api/library/import", status_code=201)
async def import_library_archive(file: UploadFile = File(...)):
    # This route is deliberately closed if deployment auth has not been set.
    # AuthMiddleware verifies the signed owner session before this handler.
    if not os.getenv("NASHR_AUTH_PASSWORD"):
        raise HTTPException(503, "Configure authentication before using browser imports.")
    data = await file.read(MAX_ARCHIVE_BYTES + 1)
    try:
        members = validate_archive(data)
    except (ValueError, UnicodeError, zipfile.BadZipFile) as exc:
        raise HTTPException(422, str(exc)) from exc
    with tempfile.TemporaryDirectory(prefix="nashr-import-") as directory:
        root = Path(directory)
        for name, payload in members:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        async with engine.connect() as connection:
            locked = (await connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_ID})).scalar()
            await connection.commit()
            if not locked:
                raise HTTPException(409, "Another library import is running. Retry after it finishes.")
            try:
                async with AsyncSession(bind=connection, expire_on_commit=False) as session:
                    result = {}
                    if (root / "content").exists():
                        result["topics"] = await import_topics(session, root, None, False)
                    if (root / "designs/index.csv").exists():
                        result["designs"] = await import_designs(session, root, None, False)
                    return {"collections": result, "review_status": "DRAFT", "published": False}
            finally:
                await connection.rollback()
                await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_ID})
                await connection.commit()


@router.get("/library/import", response_class=HTMLResponse)
async def library_import_page():
    return HTMLResponse('''<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>استيراد مكتبة المحتوى</title>
<style>body{font:16px system-ui;background:#10151f;color:#e7ebf2;max-width:850px;margin:60px auto;padding:24px}section{padding:30px;border:1px solid #354157;border-radius:18px;background:#192334}button,input{padding:14px;margin:12px 0;max-width:100%}button{background:#a2edce;color:#102a20;border:0;border-radius:8px;font-weight:700}pre{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.8}a{color:#a2edce}</style>
<a href="/publishing">العودة إلى النشر</a><h1>استيراد مكتبة المحتوى</h1><section>
<p>اختر حزم ZIP المجهزة من Engineering540. حد الحزمة25MiB، وحتى100مادة. يستمر الاستيراد حزمة بعد حزمة، ويمكن إعادة المحاولة دون تكرار المواد المكتملة.</p>
<p>كل المواد تبقى مسودات للمراجعة. لا اعتماد ولا جدولة ولا نشر تلقائي.</p>
<label for="archives">حزم المكتبة</label><br><input id="archives" type="file" accept=".zip" multiple><br>
<button id="start">بدء الاستيراد</button><pre id="result" role="status" aria-live="polite"></pre></section>
<script>const start=document.getElementById('start'),out=document.getElementById('result');start.onclick=async()=>{const files=[...document.getElementById('archives').files];if(!files.length){out.textContent='اختر حزمة أولاً';return}start.disabled=true;out.textContent='';try{for(const file of files){out.textContent+='جارٍ: '+file.name+'\\n';const form=new FormData();form.append('file',file);const r=await fetch('/api/library/import',{method:'POST',body:form}),d=await r.json();if(!r.ok)throw Error(d.detail||r.status);for(const [name,v] of Object.entries(d.collections)){out.textContent+=name+': جديد '+v.imported.length+'، سابق '+v.skipped.length+'، تعذر '+v.failed.length+'\\n';if(v.failed.length)throw Error(v.failed.join('\\n'))}}out.textContent+='اكتمل. جميع المواد مسودات.'}catch(e){out.textContent+='توقف: '+e.message+'\\nيمكن إعادة الحزم المكتملة بأمان.'}finally{start.disabled=false}};</script></html>''')
