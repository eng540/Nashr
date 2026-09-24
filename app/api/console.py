"""Embedded HTML interface for the Nashr test console."""

NASHR_CONSOLE_HTML = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Nashr Console</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>tailwind.config={darkMode:'class'};</script>
</head>
<body class="min-h-screen bg-slate-50 text-slate-900 antialiased dark:bg-slate-950 dark:text-slate-100">
  <main class="mx-auto max-w-5xl px-4 py-8 sm:px-6 lg:px-8">
    <header class="mb-8 flex items-center justify-between gap-4">
      <div>
        <p class="text-sm font-medium text-indigo-600 dark:text-indigo-400">Nashr</p>
        <h1 class="mt-1 text-3xl font-bold">Nashr Console</h1>
        <p class="mt-2 text-sm text-slate-600 dark:text-slate-400">رفع PDF، استخراج الأفكار، ثم نشر الفكرة المختارة في تيليجرام.</p>
      </div>
      <button id="theme-toggle" class="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm shadow-sm dark:border-slate-800 dark:bg-slate-900">◐ الوضع</button>
    </header>

    <section class="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div class="flex flex-col gap-4 sm:flex-row sm:items-end">
        <label class="flex-1">
          <span class="mb-2 block text-sm font-semibold">ملف PDF</span>
          <input id="pdf-file" type="file" accept="application/pdf" class="block w-full rounded-xl border border-slate-300 bg-slate-50 p-3 text-sm dark:border-slate-700 dark:bg-slate-950">
        </label>
        <button id="upload-btn" class="rounded-xl bg-indigo-600 px-6 py-3 font-semibold text-white transition hover:bg-indigo-700 disabled:opacity-50">رفع واستخراج</button>
      </div>
      <div id="progress" class="mt-5 hidden">
        <div class="flex items-center gap-3 text-sm text-slate-600 dark:text-slate-400">
          <span class="h-4 w-4 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent"></span>
          <span id="progress-text"></span>
        </div>
      </div>
      <div id="error" class="mt-4 hidden rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300"></div>
    </section>

    <section id="ideas-section" class="mt-8 hidden">
      <div class="mb-4 flex items-end justify-between">
        <div>
          <h2 class="text-xl font-bold">الأفكار الخمس المستخرجة</h2>
          <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">اختر إحدى الأفكار لإنشاء مسودة النشر.</p>
        </div>
        <span id="idea-count" class="rounded-full bg-slate-100 px-3 py-1 text-xs dark:bg-slate-800"></span>
      </div>
      <div id="ideas" class="grid gap-4 md:grid-cols-2"></div>
    </section>

    <section id="draft-section" class="mt-8 hidden">
      <div class="rounded-2xl border border-indigo-200 bg-indigo-50/70 p-5 dark:border-indigo-900 dark:bg-indigo-950/30">
        <h2 class="text-xl font-bold">معاينة المسودة</h2>
        <div id="draft-content" class="mt-4 whitespace-pre-wrap rounded-xl border border-indigo-100 bg-white p-4 text-sm leading-7 dark:border-indigo-900 dark:bg-slate-950"></div>
        <button id="publish-btn" class="mt-5 w-full rounded-xl bg-emerald-600 px-6 py-4 text-lg font-bold text-white transition hover:bg-emerald-700 disabled:opacity-50">🚀 نشر في تيليجرام</button>
      </div>
    </section>

    <section id="success-section" class="mt-8 hidden">
      <div class="rounded-2xl border border-emerald-200 bg-emerald-50 p-6 dark:border-emerald-900 dark:bg-emerald-950/30">
        <h2 class="text-xl font-bold text-emerald-800 dark:text-emerald-300">✓ تم النشر بنجاح</h2>
        <p class="mt-1 text-sm text-emerald-700 dark:text-emerald-400">تم إرسال المنشور إلى القناة وتسجيل العملية في سجل Nashr.</p>
        <p class="mt-3 text-xs text-slate-500 dark:text-slate-400">معرف رسالة تيليجرام</p>
        <code id="external-id" class="mt-1 block break-all rounded-lg bg-white/70 p-2 text-sm font-mono dark:bg-slate-950/60"></code>
      </div>
    </section>
  </main>

  <script>
    const $ = id => document.getElementById(id);
    const state = { publicationId: null };

    function busy(v, msg) {
      $('upload-btn').disabled = v;
      $('publish-btn').disabled = v;
      $('progress').classList.toggle('hidden', !v);
      if (msg) $('progress-text').textContent = msg;
    }

    function error(m) {
      $('error').textContent = m;
      $('error').classList.remove('hidden');
    }

    function clearError() {
      $('error').classList.add('hidden');
    }

    function escapeHtml(t) {
      return (t || '').toString()
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    async function request(url, opt = {}) {
      const r = await fetch(url, opt);
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw Error(d.detail || 'حدث خطأ غير متوقع.');
      return d;
    }

    function renderIdeas(units) {
      $('ideas').innerHTML = units.map((u, i) => {
        const id = (typeof u === 'object' && u.id) ? u.id : u;
        const title = (typeof u === 'object' && u.title) ? u.title : ('فكرة #' + (i + 1));
        const content = (typeof u === 'object' && u.content) ? u.content : '';
        const position = (typeof u === 'object' && u.position) ? u.position : (i + 1);

        return `
          <button data-id="${escapeHtml(id)}" class="idea-card text-right rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-indigo-400 dark:border-slate-800 dark:bg-slate-900">
            <div class="mb-3 flex items-center justify-between">
              <span class="inline-flex h-7 w-7 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">${position}</span>
              <span class="text-xs text-slate-400">انقر للاختيار</span>
            </div>
            <h3 class="mb-1 text-sm font-bold text-slate-900 dark:text-slate-100">${escapeHtml(title)}</h3>
            <p class="text-xs leading-relaxed text-slate-600 line-clamp-3 dark:text-slate-400">${escapeHtml(content)}</p>
          </button>
        `;
      }).join('');

      document.querySelectorAll('.idea-card').forEach(b => {
        b.onclick = () => selectIdea(b.dataset.id, b);
      });
    }

    async function selectIdea(id, buttonEl) {
      clearError();
      document.querySelectorAll('.idea-card').forEach(x => x.classList.remove('border-indigo-500', 'ring-2', 'ring-indigo-500/20'));
      buttonEl.classList.add('border-indigo-500', 'ring-2', 'ring-indigo-500/20');

      busy(true, 'جاري إنشاء المسودة...');
      try {
        const d = await request('/knowledge-units/' + id + '/draft', { method: 'POST' });
        state.publicationId = d.id;
        $('draft-content').textContent = d.content || '';
        $('draft-section').classList.remove('hidden');$('draft-section').scrollIntoView({ behavior: 'smooth' });
      } catch (e) {
        error(e.message);
      } finally {
        busy(false);
      }
    }

    $('upload-btn').onclick = async () => {
      clearError();
      const file = $('pdf-file').files[0];
      if (!file) {
        error('اختر ملف PDF أولاً.');
        return;
      }

      const form = new FormData();
      form.append('file', file);

      $('ideas-section').classList.add('hidden');
      $('draft-section').classList.add('hidden');$('success-section').classList.add('hidden');

      busy(true, 'جاري رفع الملف وحفظه...');
      try {
        const source = await request('/sources', { method: 'POST', body: form });
        busy(true, 'تم الرفع بنجاح. جاري استخراج الأفكار عبر الذكاء الاصطناعي...');
        const extraction = await request('/sources/' + source.id + '/extract', { method: 'POST' });
        
        renderIdeas(extraction.knowledge_units || extraction.knowledge_unit_ids || []);
        $('idea-count').textContent = (extraction.count || 0) + ' أفكار';
        $('ideas-section').classList.remove('hidden');$('ideas-section').scrollIntoView({ behavior: 'smooth' });
      } catch (e) {
        error(e.message);
      } finally {
        busy(false);
      }
    };

    $('publish-btn').onclick = async () => {
      if (!state.publicationId) return;
      clearError();
      busy(true, 'جاري النشر في قناة تيليجرام...');
      try {
        const result = await request('/publications/' + state.publicationId + '/publish', { method: 'POST' });
        if (result.status !== 'PUBLISHED') throw Error(result.error_message || 'تعذر تأكيد النشر.');
        $('external-id').textContent = result.external_id || 'غير متاح';
        $('success-section').classList.remove('hidden');$('success-section').scrollIntoView({ behavior: 'smooth' });
      } catch (e) {
        error(e.message);
      } finally {
        busy(false);
      }
    };

    $('theme-toggle').onclick = () => document.documentElement.classList.toggle('dark');
  </script>
</body>
</html>
"""