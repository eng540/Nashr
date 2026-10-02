"""Embedded HTML interface for the Nashr editorial workspace."""

NASHR_CONSOLE_HTML = '''<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Nashr — مساحة العمل</title><script src="https://cdn.tailwindcss.com"></script>
<style>
  body{font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
  .step{transition:all .2s ease}.step.active{border-color:#4f46e5;background:#eef2ff}.step.done{border-color:#10b981;background:#ecfdf5}
  .drop-zone{transition:all .2s ease}.drop-zone.dragging,.drop-zone:focus-within{border-color:#4f46e5;background:#eef2ff}
  .material-card{transition:transform .15s ease,box-shadow .15s ease,border-color .15s ease}.material-card:hover{transform:translateY(-1px);box-shadow:0 8px 20px rgb(15 23 42 / .08)}
</style>
</head>
<body class="min-h-screen bg-slate-50 text-slate-900">
<main class="mx-auto max-w-6xl px-4 py-8 sm:py-12">
<header class="mb-8 flex flex-wrap items-start justify-between gap-4 border-b pb-6">
  <div><p class="text-sm font-semibold text-indigo-600">Nashr — مساحة العمل</p>
    <h1 class="mt-1 text-3xl font-bold tracking-tight">مكتبة الكتب والمخزون التحريري</h1>
    <p class="mt-2 max-w-2xl text-sm leading-7 text-slate-600">أضف كتابًا، راقب تحليله، ثم اختر مادة وحوّلها إلى مسودة قابلة للمراجعة والنشر.</p>
  </div>
  <nav class="flex flex-wrap gap-2 text-sm" aria-label="التنقل الرئيسي"><span class="rounded-full bg-indigo-50 px-3 py-2 font-semibold text-indigo-700">📚 المكتبة</span><a href="/posts/workspace" class="rounded-full bg-white px-3 py-2 font-semibold text-slate-600 shadow-sm hover:text-indigo-600">✍️ المنشورات</a><a href="/console#scheduling-section" class="rounded-full bg-white px-3 py-2 font-semibold text-slate-600 shadow-sm hover:text-indigo-600">📅 الجدولة</a><a href="/benchmark" class="rounded-full bg-white px-3 py-2 font-semibold text-slate-600 shadow-sm hover:text-indigo-600">مختبر الجودة</a></nav>
</header>

<section class="mb-6 grid gap-3 sm:grid-cols-3" aria-label="رحلة العمل">
  <div id="step-1" class="step active rounded-2xl border-2 p-4"><p class="text-xs font-bold text-indigo-600">01</p><p class="mt-1 font-bold">المكتبة</p><p class="mt-1 text-xs text-slate-500">أضف الكتاب وافهم خريطته ومواده</p></div>
  <a href="/posts/workspace" class="step rounded-2xl border-2 border-slate-200 bg-white p-4 block hover:border-indigo-300"><p class="text-xs font-bold text-slate-400">02</p><p class="mt-1 font-bold">المنشورات</p><p class="mt-1 text-xs text-slate-500">أنشئ Posts، حررها وراجعها واعتمدها</p></a>
  <a href="/console#scheduling-section" class="step rounded-2xl border-2 border-slate-200 bg-white p-4 block hover:border-indigo-300"><p class="text-xs font-bold text-slate-400">03</p><p class="mt-1 font-bold">الجدولة</p><p class="mt-1 text-xs text-slate-500">رتب المعتمدين وحدد أوقات النشر</p></a>
</section>

<section id="post-bank-section" class="hidden mb-8 rounded-3xl border bg-white p-5 shadow-sm sm:p-7" aria-labelledby="post-bank-heading">
  <div class="flex flex-wrap items-start justify-between gap-4">
    <div><p class="text-xs font-bold text-indigo-600">Post Bank</p><h2 id="post-bank-heading" class="mt-1 text-2xl font-bold">المخزون التحريري</h2>
      <p class="mt-2 max-w-3xl text-sm leading-7 text-slate-600">تصفح المنشورات الناتجة، صفِّها، افتح أصلها، وعدّل النص المحرر دون إعادة تشغيل الإنتاج.</p></div>
    <div class="flex flex-wrap items-center gap-2"><span id="post-selection-count" class="rounded-full bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700">0 محدد</span><button id="post-bulk-approve" disabled class="rounded-lg bg-emerald-600 px-3 py-2 text-xs font-bold text-white disabled:cursor-not-allowed disabled:opacity-40">اعتماد المحدد</button><button id="post-select-all-approved" class="rounded-lg border px-3 py-2 text-xs font-semibold hover:border-indigo-400">تحديد كل القابلين للنشر</button><button id="post-clear-selection" class="rounded-lg border px-3 py-2 text-xs font-semibold hover:border-indigo-400">إلغاء التحديد</button></div>
  </div>
  <div class="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-5">
    <input id="post-search" type="search" placeholder="ابحث في العنوان أو المحتوى..." class="rounded-xl border bg-slate-50 p-3 text-sm xl:col-span-2">
    <select id="post-source" class="rounded-xl border bg-slate-50 p-3 text-sm"><option value="">كل الكتب</option></select>
    <select id="post-topic" class="rounded-xl border bg-slate-50 p-3 text-sm"><option value="">كل المحاور</option></select>
    <select id="post-status" class="rounded-xl border bg-slate-50 p-3 text-sm"><option value="">كل الحالات</option><option value="DRAFT">DRAFT — يحتاج مراجعة</option><option value="APPROVED">APPROVED — جاهز للجدولة</option><option value="REJECTED">REJECTED — يحتاج تعديل</option></select>
    <select id="post-publication-state" class="rounded-xl border bg-slate-50 p-3 text-sm"><option value="UNPUBLISHED">غير منشور</option><option value="ELIGIBLE">قابل للنشر</option><option value="">كل حالات النشر</option><option value="PUBLISHED">منشور سابقًا</option><option value="SCHEDULED">موجود في خطة</option></select>
  </div>
  <div id="post-bank-action-message" class="mt-4 hidden rounded-xl border p-3 text-sm" role="status" aria-live="polite"></div>
  <div class="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs text-slate-500">
    <span id="post-bank-summary">جارٍ التحميل...</span>
    <div class="flex gap-2"><button id="post-clear-filters" class="rounded-lg border px-3 py-2 font-semibold hover:border-indigo-400">مسح التصفية</button><button id="post-refresh" class="rounded-lg border px-3 py-2 font-semibold hover:border-indigo-400">تحديث</button></div>
  </div>
  <div id="post-bank-grid" class="mt-5 grid gap-4 lg:grid-cols-2"></div>
  <div id="post-bank-empty" class="mt-5 hidden rounded-2xl border border-dashed bg-slate-50 p-8 text-center"><p class="font-bold">لا توجد Posts مطابقة</p><p class="mt-1 text-sm text-slate-500">جرّب تغيير الفلاتر أو أنشئ Posts عبر Production Job.</p></div>
  <div class="mt-5 flex items-center justify-between"><button id="post-prev" class="rounded-xl border px-4 py-2 text-sm font-semibold disabled:opacity-40">السابق</button><span id="post-page" class="text-xs text-slate-500"></span><button id="post-next" class="rounded-xl border px-4 py-2 text-sm font-semibold disabled:opacity-40">التالي</button></div>
</section>
<section id="scheduling-section" class="mb-8 rounded-3xl border bg-white p-5 shadow-sm sm:p-7" aria-labelledby="scheduling-heading">
  <div class="flex flex-wrap items-start justify-between gap-4">
    <div><p class="text-xs font-bold text-indigo-600">07 — خطة النشر</p><h2 id="scheduling-heading" class="mt-1 text-2xl font-bold">بناء خطة النشر</h2><p class="mt-2 max-w-3xl text-sm leading-7 text-slate-600">راجع الاختيار، رتّب المنشورات وحدد البداية والفاصل، ثم راجع الخطة كاملة قبل تفعيل النشر الآلي.</p></div>
    <button id="schedule-from-selection" class="rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-bold text-white disabled:cursor-not-allowed disabled:opacity-40">إنشاء خطة من المحدد</button>
  </div>
  <div class="mt-5 grid gap-2 sm:grid-cols-5" aria-label="مراحل النشر">
    <div class="rounded-xl bg-slate-50 p-3 text-xs"><b>✓ الاختيار</b><span class="mt-1 block text-slate-500">منشورات معتمدة</span></div>
    <div class="rounded-xl bg-indigo-50 p-3 text-xs text-indigo-800"><b>→ خطة النشر</b><span class="mt-1 block">أنت هنا</span></div>
    <div class="rounded-xl bg-slate-50 p-3 text-xs"><b>المراجعة النهائية</b><span class="mt-1 block text-slate-500">فحص الجاهزية</span></div>
    <div class="rounded-xl bg-slate-50 p-3 text-xs"><b>النشر الآلي</b><span class="mt-1 block text-slate-500">تفعيل التنفيذ</span></div>
    <div class="rounded-xl bg-slate-50 p-3 text-xs"><b>السجل</b><span class="mt-1 block text-slate-500">Publication Ledger</span></div>
  </div>
  <div id="schedule-create-panel" class="mt-5 hidden rounded-2xl border bg-slate-50 p-4">
    <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      <input id="schedule-name" class="rounded-xl border bg-white p-3 text-sm" placeholder="اسم الخطة">
      <input id="schedule-timezone" class="rounded-xl border bg-white p-3 text-sm" value="Asia/Aden">
      <input id="schedule-start-at" type="datetime-local" class="rounded-xl border bg-white p-3 text-sm">
      <input id="schedule-interval" type="number" min="1" max="10080" value="30" class="rounded-xl border bg-white p-3 text-sm" placeholder="الفاصل بالدقائق">
    </div>
    <p class="mt-2 text-xs leading-6 text-slate-500">اختر وقت البداية والفاصل بالدقائق. سيولد Nashr المواعيد بالتسلسل حسب ترتيب العناصر. يمكنك تغيير ترتيب العناصر قبل الحفظ.</p>
    <div id="schedule-selection-rows" class="mt-4 space-y-2"></div>
    <div class="mt-4 flex justify-end gap-2"><button id="schedule-cancel-create" class="rounded-xl border px-4 py-2 text-sm">إلغاء</button><button id="schedule-save-create" class="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-bold text-white">حفظ الخطة</button></div>
    <p id="schedule-create-error" class="mt-2 text-sm text-red-600"></p>
  </div>
  <div class="mt-6 flex items-center justify-between"><h3 class="font-bold">الخطط المحفوظة</h3><button id="schedule-refresh" class="rounded-lg border px-3 py-2 text-xs font-semibold">تحديث</button></div>
  <div id="schedule-list" class="mt-4 space-y-3"></div>
  <div id="schedule-detail" class="mt-5 hidden rounded-2xl border bg-slate-50 p-4"></div>
  <section id="activation-confirm" class="fixed inset-0 z-50 hidden grid place-items-center bg-slate-900/60 p-4">
    <div class="w-full max-w-xl rounded-3xl bg-white p-6 shadow-2xl">
      <p class="text-xs font-bold text-indigo-600">المراجعة النهائية</p><h2 class="mt-1 text-2xl font-bold">تفعيل النشر الآلي؟</h2>
      <div id="activation-confirm-summary" class="mt-4 rounded-2xl bg-slate-50 p-4 text-sm leading-7"></div>
      <p class="mt-3 text-xs leading-6 text-slate-500">بعد التفعيل سيبدأ Nashr بتنفيذ العناصر المستحقة تلقائيًا عبر نظام النشر الحالي.</p>
      <div class="mt-5 flex flex-wrap justify-end gap-2"><button id="activation-confirm-cancel" class="rounded-xl border px-4 py-2.5 font-bold">العودة للمراجعة</button><button id="activation-confirm-ok" class="rounded-xl bg-emerald-600 px-5 py-2.5 font-bold text-white">نعم، فعّل النشر الآلي</button></div>
      <p id="activation-confirm-error" class="mt-3 text-sm text-rose-600"></p>
    </div>
  </section>
  <div class="mt-6"><div class="flex flex-wrap items-center justify-between gap-3"><h3 class="font-bold">التقويم اليومي</h3><div class="flex items-center gap-2"><input id="calendar-date" type="date" class="rounded-lg border bg-white px-3 py-2 text-xs"><button id="calendar-refresh" class="rounded-lg border px-3 py-2 text-xs font-semibold">عرض اليوم</button></div></div><div id="calendar-list" class="mt-3 space-y-2"></div></div>
  <div class="mt-6"><h3 class="font-bold">القادم</h3><div id="upcoming-list" class="mt-3 space-y-2"></div></div>
</section>
<section id="telegram-preview" class="fixed inset-0 z-50 hidden grid place-items-center bg-slate-900/60 p-4">
  <div class="w-full max-w-3xl rounded-3xl bg-white p-5 shadow-2xl sm:p-7">
    <div class="flex items-center justify-between gap-3"><div><p class="text-xs font-bold text-indigo-600">Telegram Preview</p><h2 class="text-xl font-bold">المعاينة النهائية</h2></div><button id="telegram-preview-close" class="rounded-xl border px-3 py-2 text-sm">إغلاق</button></div>
    <p id="telegram-preview-meta" class="mt-3 text-xs text-slate-500"></p>
    <pre id="telegram-preview-content" dir="rtl" class="mt-4 max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-2xl border bg-slate-50 p-5 text-sm leading-8"></pre>
  </div>
</section>
<section id="post-editor" class="fixed inset-0 z-50 hidden grid place-items-center bg-slate-900/50 p-4">
  <div class="w-full max-w-3xl rounded-3xl bg-white p-5 shadow-2xl sm:p-7">
    <div class="flex items-start justify-between gap-4"><div><p class="text-xs font-bold text-indigo-600">المراجعة التحريرية</p><h2 id="post-editor-title" class="mt-1 text-xl font-bold"></h2><div class="mt-2 flex flex-wrap items-center gap-2"><span id="post-editor-status" class="rounded-full bg-slate-100 px-3 py-1 text-xs font-bold"></span><span id="post-editor-reviewed-at" class="text-xs text-slate-400"></span></div><p id="post-editor-provenance" class="mt-1 text-xs text-slate-500"></p><div id="post-editor-source" class="mt-3 rounded-xl bg-slate-50 p-3 text-xs leading-6 text-slate-600"></div></div><button id="post-editor-close" class="rounded-xl border px-3 py-2 text-sm">إغلاق</button></div>
    <textarea id="post-editor-content" dir="rtl" class="mt-5 min-h-[300px] w-full rounded-2xl border p-4 leading-8"></textarea>
    <div class="mt-4 rounded-2xl border bg-slate-50 p-4"><label for="post-review-note" class="block text-sm font-bold">ملاحظة المراجعة</label><textarea id="post-review-note" dir="rtl" class="mt-2 min-h-20 w-full rounded-xl border bg-white p-3 text-sm leading-7" placeholder="ملاحظة اختيارية عند الاعتماد، وسبب الرفض عند الرفض."></textarea></div>
    <p id="post-editor-review-help" class="mt-3 text-xs leading-6 text-slate-500"></p>
    <div class="mt-4 flex flex-wrap items-center justify-between gap-3"><span id="post-editor-error" class="text-sm text-red-600"></span><div class="flex gap-2"><button id="post-editor-save" class="rounded-xl border px-4 py-2.5 font-bold">حفظ التعديل وإعادة المراجعة</button><button id="post-editor-reject" class="rounded-xl bg-rose-600 px-5 py-2.5 font-bold text-white">رفض</button><button id="post-editor-approve" class="rounded-xl bg-emerald-600 px-5 py-2.5 font-bold text-white">اعتماد</button></div></div>
  </div>
</section>
<section class="rounded-3xl border bg-white p-5 shadow-sm sm:p-7" aria-labelledby="source-heading">
  <div class="mb-5"><h2 id="source-heading" class="text-xl font-bold">ابدأ من مكتبتك</h2><p class="mt-1 text-sm text-slate-500">يمكنك متابعة كتاب محفوظ أو إضافة كتاب PDF جديد.</p></div>
  <div class="grid gap-6 lg:grid-cols-2">
    <div><label for="source-select" class="mb-2 block text-sm font-bold">اختر كتابًا محفوظًا</label>
      <div class="flex gap-2"><select id="source-select" aria-describedby="source-help" class="min-w-0 flex-1 rounded-xl border bg-slate-50 p-3 text-sm"></select><button id="source-btn" class="rounded-xl bg-slate-800 px-5 py-3 font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50">فتح مساحة الكتاب</button></div>
      <p id="source-help" class="mt-2 text-xs text-slate-500">اختر كتابًا لمعرفة حالته ومتابعة تحليله.</p>
    </div>
    <div><label for="pdf-file" class="mb-2 block text-sm font-bold">أضف كتابًا جديدًا</label>
      <div id="drop-zone" tabindex="0" class="drop-zone cursor-pointer rounded-2xl border-2 border-dashed border-slate-300 bg-slate-50 p-4 text-center">
        <input id="pdf-file" type="file" accept="application/pdf" class="sr-only">
        <p class="font-semibold text-slate-700">اسحب ملف PDF هنا</p><p class="mt-1 text-xs text-slate-500">أو اضغط لاختيار ملف من جهازك — الحد الأقصى 100 MB</p>
        <p id="file-name" class="mt-3 hidden rounded-lg bg-white px-3 py-2 text-xs font-semibold text-indigo-700"></p>
      </div><button id="upload-btn" class="mt-3 w-full rounded-xl bg-indigo-600 px-5 py-3 font-semibold text-white transition hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50">رفع وتحليل الكتاب</button>
    </div>
  </div>
  <div id="empty-library" class="mt-6 hidden rounded-2xl border border-dashed bg-slate-50 p-6 text-center"><p class="font-bold">لم تضف أي كتاب بعد</p><p class="mt-1 text-sm text-slate-500">ابدأ برفع ملف PDF من المنطقة أعلاه.</p></div>
  <div id="progress" class="mt-6 hidden rounded-2xl border border-indigo-100 bg-indigo-50 p-4" role="status" aria-live="polite"><div class="flex items-center justify-between gap-4"><span id="progress-message" class="text-sm font-semibold text-indigo-900"></span><span id="progress-percent" class="text-xs font-bold text-indigo-700"></span></div><div class="mt-3 h-2 overflow-hidden rounded-full bg-indigo-100"><div id="progress-bar" class="h-full rounded-full bg-indigo-600 transition-all" style="width:0%"></div></div></div>
  <div id="error" class="mt-4 hidden rounded-2xl border border-red-200 bg-red-50 p-4 text-sm leading-7 text-red-700" role="alert"></div>
  <div id="retry-box" class="mt-4 hidden rounded-2xl border border-amber-200 bg-amber-50 p-4"><p class="text-sm font-semibold text-amber-900">توقف التحليل قبل اكتماله.</p><p class="mt-1 text-xs text-amber-800">تم الاحتفاظ بالكتاب ويمكنك إعادة المحاولة دون رفعه من جديد.</p><button id="retry-btn" class="mt-3 rounded-xl bg-amber-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-amber-700">إعادة المحاولة</button></div>
</section>

<section id="book-section" class="mt-8 hidden" aria-labelledby="book-title">
  <div class="rounded-3xl border bg-white p-5 shadow-sm sm:p-7"><div class="flex flex-wrap items-start justify-between gap-4"><div><p class="text-xs font-bold text-indigo-600">مساحة الكتاب</p><h2 id="book-title" class="mt-1 text-2xl font-bold"></h2><p id="book-description" class="mt-2 max-w-3xl text-sm leading-7 text-slate-600"></p></div><div class="flex flex-wrap gap-2"><a href="/posts/workspace" class="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-bold text-white hover:bg-indigo-700">✍️ افتح مصنع المنشورات</a><button id="refresh-btn" class="rounded-xl border px-4 py-2 text-sm font-semibold text-slate-600 hover:border-indigo-400 hover:text-indigo-600">تحديث الحالة</button></div></div><div class="mt-5 flex flex-wrap gap-2 text-xs"><span id="topic-count" class="rounded-full bg-slate-100 px-3 py-1.5"></span><span id="material-count" class="rounded-full bg-slate-100 px-3 py-1.5"></span><span id="book-status" class="rounded-full bg-slate-100 px-3 py-1.5"></span></div></div>
  <div id="material-toolbar" class="mt-5 hidden rounded-2xl border bg-white p-4 shadow-sm"><div class="flex flex-col gap-3 lg:flex-row lg:items-center"><label class="min-w-0 flex-1"><span class="sr-only">البحث في المواد</span><input id="material-search" type="search" placeholder="ابحث في العناوين والمحتوى..." class="w-full rounded-xl border bg-slate-50 p-3 text-sm"></label><select id="material-kind" class="rounded-xl border bg-slate-50 p-3 text-sm"><option value="">كل التصنيفات</option></select><select id="material-sort" class="rounded-xl border bg-slate-50 p-3 text-sm"><option value="position">الترتيب الأصلي</option><option value="title">العنوان: أ - ي</option><option value="kind">التصنيف</option></select><button id="collapse-topics" class="rounded-xl border px-4 py-3 text-sm font-semibold text-slate-600 hover:border-indigo-400 hover:text-indigo-600">طيّ المحاور</button></div><div class="mt-3 flex items-center justify-between text-xs text-slate-500"><span id="material-result-count"></span><button id="clear-material-filters" class="font-semibold text-indigo-600 hover:underline">مسح التصفية</button></div></div>
  <div id="topics" class="mt-5 space-y-4"></div><div id="topics-empty" class="mt-5 hidden rounded-2xl border border-dashed bg-white p-8 text-center"><p class="font-bold">لم تظهر مواد بعد</p><p class="mt-1 text-sm text-slate-500">ستظهر المحاور والمواد هنا تدريجيًا أثناء التحليل.</p></div><div id="filtered-empty" class="mt-5 hidden rounded-2xl border border-dashed bg-white p-8 text-center"><p class="font-bold">لا توجد نتائج مطابقة</p><p class="mt-1 text-sm text-slate-500">جرّب تغيير البحث أو التصنيف أو الترتيب.</p></div>
</section>

<section id="draft-section" class="fixed inset-0 z-40 hidden grid place-items-center overflow-y-auto overscroll-contain bg-slate-900/40 p-3 sm:p-10" aria-labelledby="draft-heading"><div class="mx-auto max-h-[calc(100dvh-1.5rem)] w-full max-w-3xl overflow-y-auto rounded-3xl border border-indigo-200 bg-indigo-50 p-4 shadow-2xl sm:max-h-[calc(100dvh-5rem)] sm:p-7"><div class="flex items-start justify-between gap-4"><div><p class="text-xs font-bold text-indigo-700">التحرير والنشر</p><h2 id="draft-heading" class="mt-1 text-xl font-bold">مسودة المادة المختارة</h2><p class="mt-1 text-sm leading-6 text-slate-600">راجع النص وعدّله قبل إرساله إلى تيليجرام. يمكنك الإغلاق والعودة إلى نفس موضع القائمة.</p></div><button id="close-draft-btn" class="shrink-0 rounded-xl border bg-white px-3 py-2 text-sm font-semibold text-slate-600 hover:border-indigo-400" aria-label="إغلاق المحرر">إغلاق</button></div><textarea id="draft-content" dir="rtl" aria-label="محتوى المسودة" class="mt-4 min-h-[220px] w-full rounded-2xl border bg-white p-4 leading-8 shadow-sm sm:min-h-80"></textarea><button id="publish-btn" class="mt-4 w-full rounded-xl bg-emerald-600 px-5 py-3.5 font-bold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50 sm:py-4">نشر بعد المراجعة في تيليجرام</button></div></section>
<section id="success-section" class="mt-8 hidden rounded-2xl border border-emerald-200 bg-emerald-50 p-5" role="status"><h2 class="text-xl font-bold text-emerald-800">تم النشر بنجاح</h2><p class="mt-2 text-sm text-emerald-700">تم إرسال المسودة إلى تيليجرام. رقم الرسالة:</p><code id="external-id" class="mt-2 block rounded-lg bg-white p-2"></code></section>
</main>
<script>
const $=id=>document.getElementById(id);const state={sourceId:null,jobId:null,publicationId:null,pollTimer:null,selectedPostIds:[],selectedPostMeta:{},postOffset:0,postTotal:0,scheduleIdempotencyKey:null,activeScheduleId:null,pendingActivationId:null};
async function loadPostSources(){const sources=await request('/sources');$('post-source').innerHTML='<option value="">كل الكتب</option>'+sources.map(s=>'<option value="'+esc(s.id)+'">'+esc(s.book_title||s.filename)+'</option>').join('');}
async function loadPostTopics(sourceId){$('post-topic').innerHTML='<option value="">كل المحاور</option>';if(!sourceId)return;try{const d=await request('/sources/'+sourceId+'/book-map');$('post-topic').innerHTML='<option value="">كل المحاور</option>'+d.topics.map(t=>'<option value="'+esc(t.id)+'">'+esc(t.title)+'</option>').join('');}catch(e){}}
async function renderScheduleSelection(){
  const ids=window.nashrPostSelection?window.nashrPostSelection():state.selectedPostIds;
  const rows=$('schedule-selection-rows');
  const renderRows=()=>{rows.innerHTML=ids.map((id,i)=>'<div data-schedule-row="'+esc(id)+'" class="flex items-center gap-3 rounded-xl border bg-white p-3"><span class="w-7 text-xs font-bold text-slate-400">'+(i+1)+'</span><span class="min-w-0 flex-1"><b class="block truncate">'+esc(state.selectedPostMeta[id]?.title||'جاري تحميل عنوان المنشور…')+'</b><span class="block truncate text-[11px] text-slate-400">'+esc(state.selectedPostMeta[id]?.source_title||id)+'</span></span><button type="button" data-move-up="'+esc(id)+'" class="rounded-lg border px-2 py-1 text-xs">↑</button><button type="button" data-move-down="'+esc(id)+'" class="rounded-lg border px-2 py-1 text-xs">↓</button><span data-schedule-time="'+esc(id)+'" class="w-40 text-xs text-slate-500"></span></div>').join('');document.querySelectorAll('[data-move-up]').forEach(b=>b.onclick=()=>moveSelectedPost(b.dataset.moveUp,-1));document.querySelectorAll('[data-move-down]').forEach(b=>b.onclick=()=>moveSelectedPost(b.dataset.moveDown,1));updateGeneratedScheduleTimes();};
  renderRows();
  const missing=ids.filter(id=>!state.selectedPostMeta[id]);
  if(missing.length){await Promise.all(missing.map(async id=>{try{state.selectedPostMeta[id]=await request('/posts/'+id);}catch(e){state.selectedPostMeta[id]={title:'منشور '+id.slice(0,8),source_title:'تعذر تحميل التفاصيل'};}}));renderRows();}
}
function moveSelectedPost(id,direction){
  const index=state.selectedPostIds.indexOf(id);
  const target=index+direction;
  if(index<0||target<0||target>=state.selectedPostIds.length)return;
  const next=[...state.selectedPostIds];[next[index],next[target]]=[next[target],next[index]];
  state.selectedPostIds=next;renderSelectionCount();renderScheduleSelection();
}
function updateGeneratedScheduleTimes(){
  const start=$('schedule-start-at').value,interval=Number($('schedule-interval').value||0),timezone=$('schedule-timezone').value.trim();
  document.querySelectorAll('[data-schedule-time]').forEach((el,index)=>{
    if(!start||!interval||!timezone){el.textContent='';return;}
    try{
      const base=new Date(localDateTimeToUtcISOString(start,timezone));
      const when=new Date(base.getTime()+index*interval*60000);
      el.textContent=when.toLocaleString('ar',{timeZone:timezone,dateStyle:'short',timeStyle:'short'});
    }catch(e){el.textContent='وقت غير صالح';}
  });
}
function localDateTimeToUtcISOString(value,timeZone){if(!value)return null;const match=/^(\\d{4})-(\\d{2})-(\\d{2})T(\\d{2}):(\\d{2})$/.exec(value);if(!match)throw new Error('موعد غير صالح.');const [,y,m,d,h,min]=match;const wall=Date.UTC(Number(y),Number(m)-1,Number(d),Number(h),Number(min),0);const formatter=new Intl.DateTimeFormat('en-US',{calendar:'gregory',numberingSystem:'latn',timeZone,hourCycle:'h23',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit'});const parts=Object.fromEntries(formatter.formatToParts(new Date(wall)).filter(p=>p.type!=='literal').map(p=>[p.type,p.value]));const zoneWall=Date.UTC(Number(parts.year),Number(parts.month)-1,Number(parts.day),Number(parts.hour),Number(parts.minute),Number(parts.second));const candidate=new Date(wall-(zoneWall-wall));const check=Object.fromEntries(formatter.formatToParts(candidate).filter(p=>p.type!=='literal').map(p=>[p.type,p.value]));if(check.year!==y||check.month!==m||check.day!==d||check.hour!==h||check.minute!==min)throw new Error('الوقت المحدد غير صالح في المنطقة الزمنية '+timeZone+'.');return candidate.toISOString();}
async function loadSchedules(){try{const d=await request('/schedules?limit=50&offset=0');$('schedule-list').innerHTML=d.items.length?d.items.map(s=>'<button data-schedule-id="'+esc(s.id)+'" class="block w-full rounded-2xl border bg-white p-4 text-right hover:border-indigo-400"><div class="flex items-center justify-between gap-3"><strong>'+esc(s.name)+'</strong><span class="rounded-full bg-slate-100 px-2 py-1 text-xs">'+esc(s.status)+'</span></div><p class="mt-2 text-xs text-slate-500">'+s.total_items+' عناصر · '+s.published_items+' منشورة · '+s.failed_items+' فاشلة · '+(s.skipped_items||0)+' متجاوزة · التالي: '+esc(s.next_scheduled_at||'لا يوجد')+'</p></button>').join(''):'<p class="rounded-xl border border-dashed p-6 text-center text-sm text-slate-500">لا توجد خطط بعد.</p>';document.querySelectorAll('[data-schedule-id]').forEach(b=>b.onclick=()=>openSchedule(b.dataset.scheduleId));}catch(e){$('schedule-list').textContent=e.message;}}
async function showTelegramPreview(id){
  try{
    const p=await request('/posts/'+id+'/telegram-preview');
    $('telegram-preview-meta').textContent='Telegram · '+(p.destination||'لم يحدد الوجهة')+' · '+(p.status==='APPROVED'?'معتمد':'غير معتمد');
    $('telegram-preview-content').textContent=p.content||'';
    $('telegram-preview').classList.remove('hidden');
  }catch(e){alert(e.message);}
}
async function loadCalendar(){
  try{
    const date=$('calendar-date').value || new Date().toISOString().slice(0,10);
    $('calendar-date').value=date;
    const d=await request('/schedules/calendar?date='+encodeURIComponent(date)+'&timezone='+encodeURIComponent($('schedule-timezone').value||'Asia/Aden'));
    $('calendar-list').innerHTML=d.items.length?d.items.map(i=>'<button data-calendar-preview="'+esc(i.post_id)+'" class="w-full rounded-xl border bg-white p-3 text-right hover:border-indigo-400"><div class="flex flex-wrap items-center justify-between gap-3"><strong>'+esc(i.title)+'</strong><span class="text-xs text-slate-500">'+new Date(i.scheduled_at).toLocaleTimeString('ar',{hour:'2-digit',minute:'2-digit',timeZone:d.timezone})+'</span></div><p class="mt-1 text-xs text-slate-400">'+esc(i.schedule_name)+' · '+esc(i.status)+' · الموضع '+i.position+(i.last_error?' · '+esc(i.last_error):'')+'</p></button>').join(''):'<p class="rounded-xl border border-dashed p-4 text-center text-sm text-slate-500">لا توجد عناصر لهذا اليوم.</p>';
    document.querySelectorAll('[data-calendar-preview]').forEach(b=>b.onclick=()=>showTelegramPreview(b.dataset.calendarPreview));
  }catch(e){$('calendar-list').textContent=e.message;}
}
async function loadUpcoming(){
  try{
    const d=await request('/schedules/upcoming?days=7&limit=100');
    const box=$('upcoming-list');
    box.innerHTML=d.items.length?d.items.map(i=>'<button data-upcoming-preview="'+esc(i.post_id)+'" class="w-full rounded-xl border bg-white p-3 text-right hover:border-indigo-400"><div class="flex flex-wrap items-center justify-between gap-3"><strong>'+esc(i.title)+'</strong><span class="text-xs text-slate-500">'+new Date(i.scheduled_at).toLocaleString('ar',{timeZone:i.timezone})+'</span></div><p class="mt-1 text-xs text-slate-400">'+esc(i.schedule_name)+' · '+esc(i.status)+'</p></button>').join(''):'<p class="rounded-xl border border-dashed p-4 text-center text-sm text-slate-500">لا توجد منشورات قادمة في الخطط النشطة.</p>';
    document.querySelectorAll('[data-upcoming-preview]').forEach(b=>b.onclick=()=>showTelegramPreview(b.dataset.upcomingPreview));
  }catch(e){$('upcoming-list').textContent=e.message;}
}
function scheduleStatusLabel(status){return({DRAFT:'مسودة',PAUSED:'متوقفة مؤقتًا',ACTIVE:'نشطة',COMPLETED:'مكتملة',CANCELLED:'ملغاة'}[status]||status);}
function itemStatusLabel(status){return({PENDING:'بانتظار التنفيذ',PROCESSING:'قيد التنفيذ',PUBLISHED:'منشور',FAILED:'فشل',SKIPPED:'تم تجاوزه',CANCELLED:'ملغى'}[status]||status);}
function toLocalDateTimeValue(iso,timeZone){const d=new Date(iso);const f=new Intl.DateTimeFormat('en-US',{calendar:'gregory',numberingSystem:'latn',timeZone,hourCycle:'h23',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});const p=Object.fromEntries(f.formatToParts(d).filter(x=>x.type!=='literal').map(x=>[x.type,x.value]));return p.year+'-'+p.month+'-'+p.day+'T'+p.hour+':'+p.minute;}
function scheduleSummary(s){const first=s.items?.[0],last=s.items?.[s.items.length-1],next=s.next_scheduled_at;return '<div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><div class="rounded-xl bg-white p-3"><p class="text-xs text-slate-500">المنشورات</p><b class="text-lg">'+s.total_items+'</b></div><div class="rounded-xl bg-white p-3"><p class="text-xs text-slate-500">الحالة</p><b class="text-lg">'+esc(scheduleStatusLabel(s.status))+'</b></div><div class="rounded-xl bg-white p-3"><p class="text-xs text-slate-500">أول نشر</p><b class="text-sm">'+(first?esc(new Date(first.scheduled_at).toLocaleString('ar',{timeZone:s.timezone})):'—')+'</b></div><div class="rounded-xl bg-white p-3"><p class="text-xs text-slate-500">آخر نشر</p><b class="text-sm">'+(last?esc(new Date(last.scheduled_at).toLocaleString('ar',{timeZone:s.timezone})):'—')+'</b></div></div><div class="mt-3 rounded-xl border bg-white p-3 text-sm"><b>حالة التنفيذ:</b> '+s.published_items+' منشورة · '+s.pending_items+' متبقية · '+s.failed_items+' فاشلة · '+(s.skipped_items||0)+' متجاوزة'+(next?' · النشر التالي '+esc(new Date(next).toLocaleString('ar',{timeZone:s.timezone})):'');}
async function loadScheduleValidation(id){try{return await request('/schedules/'+id+'/validation');}catch(e){return {valid:false,errors:[e.message],warnings:[]};}}
function renderValidation(v){return '<div class="mt-4 rounded-2xl border '+(v.valid?'border-emerald-200 bg-emerald-50':'border-rose-200 bg-rose-50')+' p-4"><div class="flex items-center justify-between gap-3"><b>'+ (v.valid?'✓ الخطة جاهزة للتفعيل':'⚠ توجد مشاكل تمنع التفعيل')+'</b><span class="text-xs">'+(v.pending_items||0)+' بانتظار · '+(v.published_items||0)+' منشورة · '+(v.failed_items||0)+' فاشلة</span></div>'+(v.errors?.length?'<ul class="mt-3 list-disc space-y-1 pr-5 text-sm text-rose-700">'+v.errors.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>':'')+(v.warnings?.length?'<ul class="mt-3 list-disc space-y-1 pr-5 text-sm text-amber-700">'+v.warnings.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>':'')+(v.blocked_items?.length?'<div class="mt-3 rounded-xl border border-amber-200 bg-white p-3 text-sm"><b>عناصر لن توقف بقية الخطة:</b><ul class="mt-2 list-disc space-y-1 pr-5">'+v.blocked_items.map(x=>'<li>الموضع '+x.position+' — '+esc(x.message)+'</li>').join('')+'</ul></div>':'')+'</div>';}
async function openSchedule(id){try{const s=await request('/schedules/'+id);state.activeScheduleId=id;$('schedule-detail').classList.remove('hidden');const actions=(s.status==='DRAFT'||s.status==='PAUSED'?'<button data-schedule-action="activate" class="rounded-xl bg-emerald-600 px-4 py-2.5 text-xs font-bold text-white">تفعيل النشر الآلي</button>':'')+(s.status==='ACTIVE'?'<button data-schedule-action="pause" class="rounded-xl border px-4 py-2.5 text-xs font-bold">إيقاف مؤقت</button>':'')+(s.status==='DRAFT'||s.status==='ACTIVE'||s.status==='PAUSED'?'<button data-schedule-action="cancel" class="rounded-xl border px-4 py-2.5 text-xs font-bold">إلغاء الخطة</button>':'');const validation=await loadScheduleValidation(id);$('schedule-detail').innerHTML='<div class="flex flex-wrap items-start justify-between gap-3"><div><p class="text-xs font-bold text-indigo-600">مراجعة الخطة</p><h3 class="mt-1 text-xl font-bold">'+esc(s.name)+'</h3><p class="mt-1 text-xs text-slate-500">'+esc(s.timezone)+' · '+esc(scheduleStatusLabel(s.status))+'</p></div><div class="flex flex-wrap gap-2">'+actions+'</div></div><div class="mt-4">'+scheduleSummary(s)+'</div>'+renderValidation(validation)+'<div class="mt-5 space-y-2"><h4 class="font-bold">المنشورات داخل الخطة</h4>'+s.items.map(i=>'<div class="rounded-xl border bg-white p-3"><div class="flex flex-wrap items-center gap-3"><b class="w-7">'+i.position+'</b><span class="min-w-0 flex-1 font-semibold">'+esc(i.title)+'</span><span class="rounded-full bg-slate-100 px-2 py-1 text-xs">'+esc(itemStatusLabel(i.status))+'</span><button data-item-preview="'+esc(i.post_id)+'" class="rounded-lg border px-2 py-1 text-xs">معاينة</button>'+(i.status==='FAILED'?'<button data-item-retry="'+esc(i.id)+'" class="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-bold text-white">إعادة المحاولة</button>':'')+'</div><p class="mt-1 text-xs text-slate-400">'+esc(i.source_title)+' ← '+esc(i.topic_title||'بدون محور')+' · محاولات '+i.attempts+(i.last_error?' · '+esc(i.last_error):'')+'</p>'+(i.status==='PENDING'?'<div class="mt-3 flex flex-wrap items-center gap-2"><input data-item-time="'+esc(i.id)+'" type="datetime-local" value="'+esc(toLocalDateTimeValue(i.scheduled_at,s.timezone))+'" class="rounded-lg border bg-slate-50 p-2 text-xs"><button data-save-item-time="'+esc(i.id)+'" class="rounded-lg border px-3 py-2 text-xs font-semibold">حفظ الوقت</button></div>':'')+'</div>').join('')+'</div>';window.location.hash='scheduling-section';document.querySelectorAll('[data-item-preview]').forEach(b=>b.onclick=()=>showTelegramPreview(b.dataset.itemPreview));document.querySelectorAll('[data-item-retry]').forEach(b=>b.onclick=()=>retryScheduleItem(id,b.dataset.itemRetry));document.querySelectorAll('[data-save-item-time]').forEach(b=>b.onclick=()=>saveScheduleItemTime(id,b.dataset.saveItemTime,s.timezone));document.querySelectorAll('[data-schedule-action]').forEach(b=>b.onclick=()=>scheduleAction(id,b.dataset.scheduleAction));}catch(e){$('schedule-detail').textContent=e.message;}}
async function retryScheduleItem(scheduleId,itemId){try{await request('/schedules/'+scheduleId+'/items/'+itemId+'/retry',{method:'POST'});await loadSchedules();await loadUpcoming();await openSchedule(scheduleId);}catch(e){alert(e.message);}}
async function saveScheduleItemTime(scheduleId,itemId,timeZone){const input=document.querySelector('[data-item-time="'+itemId+'"]');try{if(!input?.value)throw Error('حدد وقتًا صالحًا.');const scheduledAt=localDateTimeToUtcISOString(input.value,timeZone);await request('/schedules/'+scheduleId+'/items/'+itemId,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({scheduled_at:scheduledAt})});await openSchedule(scheduleId);}catch(e){alert(e.message);}}
async function scheduleAction(id,action){if(action==='activate'){const validation=await loadScheduleValidation(id);if(!validation.valid){await openSchedule(id);return;}const s=await request('/schedules/'+id);$('activation-confirm-summary').innerHTML='<b>'+esc(s.name)+'</b><br>'+s.total_items+' منشورًا<br>المنطقة الزمنية: '+esc(s.timezone)+'<br>أول نشر: '+esc(new Date(s.items[0].scheduled_at).toLocaleString('ar',{timeZone:s.timezone}))+'<br>آخر نشر: '+esc(new Date(s.items[s.items.length-1].scheduled_at).toLocaleString('ar',{timeZone:s.timezone}))+(validation.warnings?.length?'<br><span class="text-amber-700">تنبيه: '+esc(validation.warnings.join('؛ '))+'</span>':'');state.pendingActivationId=id;$('activation-confirm-error').textContent='';$('activation-confirm').classList.remove('hidden');return;}const path=action==='retry-failed'?'/retry-failed':'/'+action;try{if(action==='cancel'&&!confirm('هل تريد إلغاء خطة النشر؟'))return;await request('/schedules/'+id+path,{method:'POST'});await loadSchedules();await loadUpcoming();await openSchedule(id);}catch(e){alert(e.message);}}

function selectedPost(id){return state.selectedPostIds.includes(id)}
function togglePostSelection(id){if(selectedPost(id))state.selectedPostIds=state.selectedPostIds.filter(x=>x!==id);else state.selectedPostIds.push(id);renderSelectionCount();}
function renderSelectionCount(){
  $('post-selection-count').textContent=state.selectedPostIds.length+' محدد';
  const selectedNonApproved=state.selectedPostIds.filter(id=>{
    const item=state.selectedPostMeta?.[id];
    return item ? item.status!=='APPROVED' : true;
  }).length;
  $('post-bulk-approve').disabled=selectedNonApproved===0;
  $('schedule-from-selection').disabled=state.selectedPostIds.length===0;
  window.nashrPostSelection=()=>[...state.selectedPostIds];
}
function statusLabel(status){return({DRAFT:'مسودة — تحتاج مراجعة',APPROVED:'معتمد — جاهز للجدولة',REJECTED:'مرفوض — يحتاج تعديل'}[status]||status);}
function publicationStateLabel(state){return({PUBLISHED:'منشور سابقًا',SCHEDULED:'موجود في خطة',ELIGIBLE:'قابل للنشر',NOT_READY:'غير جاهز'}[state]||state);}
function showPostBankMessage(message,kind='info'){
  const box=$('post-bank-action-message');
  box.textContent=message;
  box.className='mt-4 rounded-xl border p-3 text-sm '+(kind==='error'?'border-rose-200 bg-rose-50 text-rose-700':kind==='success'?'border-emerald-200 bg-emerald-50 text-emerald-700':'border-indigo-200 bg-indigo-50 text-indigo-700');
  box.classList.remove('hidden');
}
function renderPostBank(d){
  state.postTotal=d.total;
  state.postItems=d.items||[];
  state.postItems.forEach(p=>{state.selectedPostMeta[p.post_id]=p;});
  const grid=$('post-bank-grid');
  grid.innerHTML=(d.items||[]).map(p=>{
    const selectable=p.status!=='APPROVED' || p.eligible_for_scheduling;
    const selected=selectedPost(p.post_id);
    const stateText=p.published?'منشور سابقًا':p.scheduled?'موجود في خطة':p.eligible_for_scheduling?'قابل للنشر':'غير جاهز';
    return '<article class="rounded-2xl border p-4 '+(selected?'border-indigo-400 bg-indigo-50':'bg-white')+'"><div class="flex items-start justify-between gap-3"><label class="flex items-start gap-3"><input type="checkbox" '+(selected?'checked':'')+' '+(selectable?'':'disabled')+' data-select-post="'+esc(p.post_id)+'" class="mt-1 h-4 w-4"><span><h3 class="font-bold">'+esc(p.title)+'</h3><p class="mt-1 text-xs text-slate-500">'+esc(p.topic_title||'بدون محور')+' · '+esc(p.source_title)+'</p></span></label><span class="rounded-full bg-slate-100 px-2 py-1 text-[11px]">'+esc(statusLabel(p.status))+'</span></div><p class="mt-3 whitespace-pre-wrap text-sm leading-8 text-slate-700">'+esc(p.content)+'</p><div class="mt-3 flex flex-wrap items-center justify-between gap-3 text-xs"><span class="rounded-full bg-slate-100 px-2 py-1">'+esc(stateText)+'</span><div class="flex gap-2"><button data-open-post="'+esc(p.post_id)+'" class="rounded-lg border px-3 py-1.5 font-semibold text-slate-700 hover:border-indigo-400">تحرير / تفاصيل</button></div></div></article>';
  }).join('');
  document.querySelectorAll('[data-select-post]').forEach(el=>el.onchange=()=>{togglePostSelection(el.dataset.selectPost);renderPostBank({...d,items:d.items});});
  document.querySelectorAll('[data-open-post]').forEach(el=>el.onclick=()=>openPostEditor(el.dataset.openPost));
  $('post-bank-empty').classList.toggle('hidden',(d.items||[]).length>0);
  $('post-bank-summary').textContent=d.total+' Posts · '+(d.items||[]).length+' معروضة';
  const page=Math.floor(d.offset/d.limit)+1;const pages=Math.max(1,Math.ceil(d.total/d.limit));$('post-page').textContent='صفحة '+page+' من '+pages;
  $('post-prev').disabled=d.offset===0;$('post-next').disabled=d.offset+d.limit>=d.total;
  renderSelectionCount();
}
async function loadPostBank(){
  const params=new URLSearchParams();
  const source=$('post-source').value,topic=$('post-topic').value,status=$('post-status').value,q=$('post-search').value.trim(),publicationState=$('post-publication-state').value;
  if(source)params.set('source_id',source);
  if(topic)params.set('topic_id',topic);
  if(status)params.set('status',status);
  if(publicationState)params.set('publication_state',publicationState);
  if(q)params.set('q',q);
  params.set('limit','50');params.set('offset',String(state.postOffset));
  try{renderPostBank(await request('/posts?'+params.toString()));}
  catch(e){$('post-bank-summary').textContent=e.message;}
}
async function filterSelectionForScheduling(){
  const ids=[...state.selectedPostIds];
  if(!ids.length)return {eligible:[],blocked:[]};
  const chunkSize=500;
  const blocked=[];
  const blockedIds=new Set();
  for(let offset=0;offset<ids.length;offset+=chunkSize){
    const chunk=ids.slice(offset,offset+chunkSize);
    const params=new URLSearchParams();
    chunk.forEach(id=>params.append('post_ids',id));
    const result=await request('/schedules/eligibility?'+params.toString());
    (result.blocked||[]).forEach(row=>{blocked.push(row);blockedIds.add(row.post_id);});
  }
  state.selectedPostIds=ids.filter(id=>!blockedIds.has(id));
  if(blocked.length){
    showPostBankMessage('تم استبعاد '+blocked.length+' منشورًا غير قابل للنشر من خطة الجدولة: '+blocked.map(x=>x.message).join('؛ '),'info');
  }
  renderSelectionCount();
  return {eligible:state.selectedPostIds,blocked};
}

async function openPostEditor(id){try{const p=await request('/posts/'+id);$('post-editor-title').textContent=p.title;$('post-editor-status').textContent=statusLabel(p.status);$('post-editor-reviewed-at').textContent=p.reviewed_at?'آخر مراجعة: '+new Date(p.reviewed_at).toLocaleString('ar'):'لم تُراجع بعد';$('post-editor-provenance').textContent=(p.source_title||'المصدر')+' ← '+(p.topic_title||'بدون محور')+' ← '+(p.title||'المادة');$('post-editor-content').value=p.content;$('post-review-note').value=p.review_note||'';$('post-editor-source').textContent='المصدر: '+(p.source_title||'غير محدد')+' · المحور: '+(p.topic_title||'بدون محور')+' · المادة: '+(p.title||'غير محدد')+' · المرجع: '+(p.source_reference||'غير محدد')+((p.discovery_page_start||p.discovery_page_end)?' · الصفحات: '+(p.discovery_page_start||'?')+'–'+(p.discovery_page_end||'?'):'');$('post-editor-review-help').textContent=p.status==='APPROVED'?'أي تعديل على النص سيعيد الحالة إلى DRAFT ويُلغي عناصر الجدولة المعلقة للمادة.':p.status==='REJECTED'?'عدّل النص ثم احفظه لإعادته إلى DRAFT، أو اعتمده بعد اكتمال المراجعة.':'راجع النص ثم اعتمده أو ارفضه بسبب واضح.';$('post-editor').dataset.postId=id;$('post-editor-error').textContent='';$('post-editor').classList.remove('hidden');}catch(e){alert(e.message);}}
async function savePost(){const id=$('post-editor').dataset.postId,content=$('post-editor-content').value.trim();if(!content){$('post-editor-error').textContent='المحتوى لا يمكن أن يكون فارغًا.';return;}$('post-editor-save').disabled=true;try{const p=await request('/posts/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({content})});$('post-editor').classList.add('hidden');await loadPostBank();}catch(e){$('post-editor-error').textContent=e.message;}finally{$('post-editor-save').disabled=false;}}
async function reviewPost(action){const id=$('post-editor').dataset.postId;const note=$('post-review-note').value.trim();$('post-editor-error').textContent='';try{const path=action==='approve'?'/approve':'/reject';const body=action==='approve'?{note}:{reason:note};if(action==='reject'&&!note){$('post-editor-error').textContent='سبب الرفض مطلوب.';return;}const p=await request('/posts/'+id+path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});$('post-editor-status').textContent=statusLabel(p.status);$('post-editor-reviewed-at').textContent=p.reviewed_at?'آخر مراجعة: '+new Date(p.reviewed_at).toLocaleString('ar'):'';$('post-editor-review-help').textContent=p.status==='APPROVED'?'تم اعتماد Post ويمكن الآن إدخاله في Schedule.':'تم رفض Post ويحتاج إلى تعديل.';await loadPostBank();}catch(e){$('post-editor-error').textContent=e.message;}}

async function bulkApproveSelected(){
  const ids=[...state.selectedPostIds];
  const pending=ids.filter(id=>state.selectedPostMeta[id]?.status!=='APPROVED');
  if(!pending.length)return showPostBankMessage('كل المنشورات المحددة معتمدة بالفعل.','info');
  $('post-bulk-approve').disabled=true;
  try{
    const chunkSize=500;
    const results=[];
    for(let offset=0;offset<pending.length;offset+=chunkSize){
      const chunk=pending.slice(offset,offset+chunkSize);
      const result=await request('/posts/bulk-approve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({post_ids:chunk})});
      results.push(...(result.results||[]));
      (result.results||[]).forEach(x=>{
        state.selectedPostMeta[x.post_id]=state.selectedPostMeta[x.post_id]||{post_id:x.post_id};
        if(x.status==='APPROVED')state.selectedPostMeta[x.post_id].status='APPROVED';
      });
    }
    const approvedCount=results.filter(x=>x.status==='APPROVED').length;
    const failed=results.filter(x=>x.status==='FAILED');
    if(failed.length){
      showPostBankMessage('تم اعتماد '+approvedCount+' منشورًا، وتعذر اعتماد '+failed.length+'؛ '+failed.map(x=>x.message).join('؛ '),approvedCount?'success':'error');
    }else{
      showPostBankMessage('تم اعتماد '+approvedCount+' منشورًا بنجاح. المجموعة ما زالت محددة ويمكنك الانتقال إلى الجدولة.','success');
    }
    await loadPostBank();
    state.selectedPostIds=ids.filter(id=>state.selectedPostMeta[id]?.status==='APPROVED');
    renderSelectionCount();
  }catch(e){showPostBankMessage(e.message,'error');}
  finally{renderSelectionCount();}
}

function setStage(stage){for(let i=1;i<=3;i++){const el=$('step-'+i);el.classList.remove('active','done');if(i<stage)el.classList.add('done');if(i===stage)el.classList.add('active');}}
function setBusy(v){$('upload-btn').disabled=v;$('source-btn').disabled=v;$('retry-btn').disabled=v;$('publish-btn').disabled=v;}
function showProgress(message,done=0,total=0){$('progress').classList.remove('hidden');$('progress-message').textContent=message||'';const pct=total?Math.min(100,Math.round(done/total*100)):0;$('progress-percent').textContent=total?`${pct}%`:'';$('progress-bar').style.width=(total?pct:25)+'%';}
function hideProgress(){$('progress').classList.add('hidden');}
function showError(message){$('error').textContent=message;$('error').classList.remove('hidden');}
function clearError(){$('error').classList.add('hidden');$('retry-box').classList.add('hidden');}
function esc(t){return(t??'').toString().replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
async function request(url,opt={}){const r=await fetch(url,opt);const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||'تعذر تنفيذ العملية.');return d;}
function stageLabel(stage){return({QUEUED:'في قائمة الانتظار',PREPARING_DOCUMENT:'جاري تجهيز وثيقة الكتاب',BUILDING_BOOK_MAP:'جاري بناء خريطة الكتاب',DISCOVERING_MATERIALS:'جاري اكتشاف المواد داخل المحاور',FINALIZING:'جاري إنهاء المخزون',COMPLETED:'اكتمل تحليل الكتاب'}[stage]||stage||'جاري تحليل الكتاب');}
async function loadSources(){const sources=await request('/sources');const select=$('source-select');select.innerHTML='<option value="">اختر كتابًا محفوظًا...</option>'+sources.map(s=>'<option value="'+esc(s.id)+'">'+esc(s.book_title||s.filename)+'</option>').join('');$('empty-library').classList.toggle('hidden',sources.length>0);$('source-btn').disabled=!sources.length;}
function renderBook(d){$('book-title').textContent=d.book.title;$('book-description').textContent=d.book.description||'لا يوجد وصف متاح لهذا الكتاب بعد.';$('topic-count').textContent=d.topics.length+' محاور';$('material-count').textContent=d.count+' مواد';$('book-status').textContent=d.job?('الحالة: '+stageLabel(d.job.stage||d.job.status)):'جاهز للمراجعة';$('book-section').classList.remove('hidden');const kinds=new Set();const html=d.topics.map(t=>{const mats=t.materials.map(m=>{kinds.add(m.kind||'مادة');return '<button data-id="'+esc(m.id)+'" data-title="'+esc(m.title)+'" data-kind="'+esc(m.kind||'مادة')+'" data-content="'+esc(m.content)+'" data-position="'+m.position+'" class="material-card text-right rounded-2xl border bg-white p-4 hover:border-indigo-400"><div class="flex justify-between gap-3"><strong class="text-sm">'+esc(m.title)+'</strong><span class="text-xs text-slate-400">'+esc(m.kind||'مادة')+'</span></div><p class="mt-2 line-clamp-3 text-xs leading-6 text-slate-600">'+esc(m.content)+'</p><p class="mt-2 text-xs text-slate-400">'+esc(m.source_reference||'مرجع غير محدد')+'</p></button>';}).join('');return'<article data-topic class="rounded-2xl border bg-white p-5 shadow-sm"><button data-collapse class="flex w-full items-start justify-between gap-4 text-right"><div><p class="text-xs text-slate-400">المحور '+t.position+'</p><h3 class="mt-1 text-lg font-bold">'+esc(t.title)+'</h3><p class="mt-1 text-sm leading-6 text-slate-600">'+esc(t.description)+'</p></div><div class="text-left"><span class="rounded-full bg-indigo-50 px-3 py-1 text-xs text-indigo-700">'+t.materials.length+' مواد</span><p class="mt-2 text-xs text-slate-400">'+esc(t.discovery_status||'قيد التجهيز')+'</p></div></button><div data-topic-content class="mt-4 grid gap-3">'+(mats||'<p class="text-sm text-slate-400">لم تُكتشف مواد في هذا المحور حتى الآن.</p>')+'</div></article>';}).join('');$('topics').innerHTML=html;$('topics-empty').classList.toggle('hidden',d.topics.length>0);$('material-toolbar').classList.toggle('hidden',d.count===0);document.querySelectorAll('.material-card').forEach(b=>b.onclick=()=>selectMaterial(b.dataset.id));document.querySelectorAll('[data-collapse]').forEach(b=>b.onclick=()=>b.parentElement.querySelector('[data-topic-content]').classList.toggle('hidden'));populateKinds(kinds);applyMaterialFilters();}
function populateKinds(kinds){const select=$('material-kind');const current=select.value;select.innerHTML='<option value="">كل التصنيفات</option>'+Array.from(kinds).sort((a,b)=>a.localeCompare(b,'ar')).map(k=>'<option value="'+esc(k)+'">'+esc(k)+'</option>').join('');select.value=current;}
function applyMaterialFilters(){const query=$('material-search').value.trim().toLocaleLowerCase('ar');const kind=$('material-kind').value;const sort=$('material-sort').value;const cards=Array.from(document.querySelectorAll('.material-card'));cards.sort((a,b)=>{if(sort==='title')return a.dataset.title.localeCompare(b.dataset.title,'ar');if(sort==='kind')return a.dataset.kind.localeCompare(b.dataset.kind,'ar');return Number(a.dataset.position)-Number(b.dataset.position);});cards.forEach(card=>card.parentElement.appendChild(card));let visible=0;cards.forEach(card=>{const hay=(card.dataset.title+' '+card.dataset.content).toLocaleLowerCase('ar');const show=(!query||hay.includes(query))&&(!kind||card.dataset.kind===kind);card.classList.toggle('hidden',!show);if(show)visible++;});document.querySelectorAll('[data-topic]').forEach(topic=>topic.classList.toggle('hidden',topic.querySelectorAll('.material-card:not(.hidden)').length===0));$('material-result-count').textContent=visible+' من '+cards.length+' مواد معروضة';$('filtered-empty').classList.toggle('hidden',visible>0||cards.length===0);}
async function refreshBook(){if(!state.sourceId)return;try{renderBook(await request('/sources/'+state.sourceId+'/book-map'));}catch(e){showError('تعذر تحديث مساحة الكتاب الآن.');}}
async function poll(){if(!state.jobId)return;try{const d=await request('/sources/'+state.sourceId+'/discovery/status');state.jobId=d.job_id||state.jobId;setStage(2);showProgress(stageLabel(d.stage),d.topics_completed||0,d.topics_total||0);await refreshBook();if(d.status==='COMPLETED'){showProgress('اكتمل تحليل الكتاب. الخريطة والمخزون جاهزان.',d.topics_total||1,d.topics_total||1);setBusy(false);return;}if(d.status==='FAILED'){setBusy(false);$('retry-box').classList.toggle('hidden',!d.retryable);showError('تعذر إكمال تحليل الكتاب. '+(d.error||'يمكنك إعادة المحاولة الآن.'));return;}state.pollTimer=setTimeout(poll,2000);}catch(e){setBusy(false);showError(e.message);}}
async function startDiscovery(sourceId){clearError();state.sourceId=sourceId;state.jobId=null;$('draft-section').classList.add('hidden');$('success-section').classList.add('hidden');setStage(2);setBusy(true);showProgress('جاري بدء تحليل الكتاب...');try{const d=await request('/sources/'+sourceId+'/discovery',{method:'POST'});state.jobId=d.job_id;showProgress(stageLabel(d.stage),0,d.topics_total||0);await refreshBook();poll();}catch(e){setBusy(false);showError(e.message);}}
async function selectMaterial(id){clearError();setStage(3);setBusy(true);showProgress('جاري إنشاء المسودة...');try{const d=await request('/knowledge-units/'+id+'/draft',{method:'POST'});state.publicationId=d.id;$('draft-content').value=d.content||'';$('draft-section').classList.remove('hidden');document.body.classList.add('overflow-hidden');hideProgress();}catch(e){showError(e.message);}finally{setBusy(false);}}
$('source-select').onchange=()=>{clearError();if($('source-select').value)setStage(2);else setStage(1);};$('source-btn').onclick=()=>{const id=$('source-select').value;if(!id)return showError('اختر كتابًا محفوظًا أولًا.');startDiscovery(id);};
$('drop-zone').onclick=()=> $('pdf-file').click();$('drop-zone').onkeydown=e=>{if(e.key==='Enter'||e.key===' ')$('pdf-file').click();};$('drop-zone').ondragover=e=>{e.preventDefault();$('drop-zone').classList.add('dragging');};$('drop-zone').ondragleave=()=>$('drop-zone').classList.remove('dragging');$('drop-zone').ondrop=e=>{e.preventDefault();$('drop-zone').classList.remove('dragging');if(e.dataTransfer.files.length){$('pdf-file').files=e.dataTransfer.files;$('pdf-file').dispatchEvent(new Event('change'));}};$('pdf-file').onchange=()=>{const file=$('pdf-file').files[0];$('file-name').classList.toggle('hidden',!file);if(file)$('file-name').textContent=file.name+' — '+(file.size/1024/1024).toFixed(1)+' MB';};
$('upload-btn').onclick=async()=>{clearError();const file=$('pdf-file').files[0];if(!file)return showError('اختر ملف PDF أولًا.');if(file.type!=='application/pdf'&&!file.name.toLowerCase().endsWith('.pdf'))return showError('الملف المحدد ليس بصيغة PDF.');if(file.size>100*1024*1024)return showError('حجم الملف يتجاوز الحد الأقصى وهو 100 MB.');setBusy(true);showProgress('جاري رفع الكتاب وحفظه...');try{const form=new FormData();form.append('file',file);const s=await request('/sources',{method:'POST',body:form});await loadSources();$('source-select').value=s.id;startDiscovery(s.id);}catch(e){setBusy(false);showError(e.message);}};
$('retry-btn').onclick=()=>{if(state.sourceId)startRetry();};async function startRetry(){clearError();setBusy(true);showProgress('جاري إعادة تحليل الكتاب...');try{const d=await request('/sources/'+state.sourceId+'/discovery/retry',{method:'POST'});state.jobId=d.job_id;poll();}catch(e){setBusy(false);showError(e.message);}}
$('material-search').oninput=applyMaterialFilters;$('material-kind').onchange=applyMaterialFilters;$('material-sort').onchange=applyMaterialFilters;$('clear-material-filters').onclick=()=>{$('material-search').value='';$('material-kind').value='';$('material-sort').value='position';applyMaterialFilters();};$('collapse-topics').onclick=()=>{const topics=Array.from(document.querySelectorAll('[data-topic-content]'));const shouldOpen=topics.some(x=>!x.classList.contains('hidden'));topics.forEach(x=>x.classList.toggle('hidden',shouldOpen));$('collapse-topics').textContent=shouldOpen?'فتح المحاور':'طيّ المحاور';};$('close-draft-btn').onclick=()=>{$('draft-section').classList.add('hidden');document.body.classList.remove('overflow-hidden');setStage(2);};$('refresh-btn').onclick=refreshBook;$('publish-btn').onclick=async()=>{if(!state.publicationId)return;if(!confirm('هل راجعت المسودة وتريد نشرها الآن في تيليجرام؟'))return;clearError();setBusy(true);showProgress('جاري حفظ المراجعة والنشر في تيليجرام...');try{const d=await request('/publications/'+state.publicationId+'/publish',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:$('draft-content').value})});if(d.status!=='PUBLISHED')throw Error(d.error_message||'تعذر تأكيد النشر.');$('external-id').textContent=d.external_id||'غير متاح';$('success-section').classList.remove('hidden');hideProgress();}catch(e){showError(e.message);}finally{setBusy(false);}};
$('schedule-from-selection').onclick=async()=>{if(!state.selectedPostIds.length)return alert('اختر Posts أولًا من Post Bank.');try{const result=await filterSelectionForScheduling();if(!result.eligible.length)return showPostBankMessage('لا توجد منشورات قابلة للنشر في الاختيار الحالي.','error');state.scheduleIdempotencyKey=window.crypto?.randomUUID?window.crypto.randomUUID():String(Date.now())+'-'+Math.random();await renderScheduleSelection();$('schedule-create-panel').classList.remove('hidden');}catch(e){showPostBankMessage(e.message,'error');}};
$('schedule-cancel-create').onclick=()=>{$('schedule-create-panel').classList.add('hidden');state.scheduleIdempotencyKey=null;};
$('schedule-save-create').onclick=async()=>{
  const ids=window.nashrPostSelection?window.nashrPostSelection():state.selectedPostIds;
  const timezone=$('schedule-timezone').value.trim(),start=$('schedule-start-at').value,interval=Number($('schedule-interval').value||0);
  if(!$('schedule-name').value.trim())return $('schedule-create-error').textContent='اسم الخطة مطلوب.';
  if(!timezone)return $('schedule-create-error').textContent='المنطقة الزمنية مطلوبة.';
  if(!ids.length)return $('schedule-create-error').textContent='اختر Posts أولًا.';
  if(ids.length>500)return $('schedule-create-error').textContent='الخطة الواحدة تدعم 500 منشورًا كحد أقصى. تم الحفاظ على كامل الاختيار؛ قلّل الاختيار قبل حفظ هذه الخطة.';
  if(!start)return $('schedule-create-error').textContent='وقت البداية مطلوب.';
  if(!interval||interval<1)return $('schedule-create-error').textContent='الفاصل بالدقائق مطلوب.';
  $('schedule-save-create').disabled=true;
  try{
    const startAt=localDateTimeToUtcISOString(start,timezone);
    const created=await request('/schedules',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('schedule-name').value.trim(),timezone,post_ids:ids,start_at:startAt,interval_minutes:interval,idempotency_key:state.scheduleIdempotencyKey})});
    $('schedule-create-panel').classList.add('hidden');$('schedule-create-error').textContent='';state.scheduleIdempotencyKey=null;await loadSchedules();await loadUpcoming();await openSchedule(created.id);
  }catch(e){$('schedule-create-error').textContent=e.message;}finally{$('schedule-save-create').disabled=false;}
};
$('activation-confirm-cancel').onclick=()=>{$('activation-confirm').classList.add('hidden');state.pendingActivationId=null;};
$('activation-confirm-ok').onclick=async()=>{const id=state.pendingActivationId;if(!id)return;$('activation-confirm-ok').disabled=true;$('activation-confirm-error').textContent='';try{await request('/schedules/'+id+'/activate',{method:'POST'});$('activation-confirm').classList.add('hidden');state.pendingActivationId=null;await loadSchedules();await loadUpcoming();await openSchedule(id);}catch(e){$('activation-confirm-error').textContent=e.message;}finally{$('activation-confirm-ok').disabled=false;}};
$('schedule-refresh').onclick=()=>{loadSchedules();loadUpcoming();loadCalendar();};
$('calendar-refresh').onclick=loadCalendar;
$('calendar-date').value=new Date().toISOString().slice(0,10);
$('schedule-start-at').onchange=updateGeneratedScheduleTimes;$('schedule-interval').oninput=updateGeneratedScheduleTimes;$('schedule-timezone').oninput=updateGeneratedScheduleTimes;
$('telegram-preview-close').onclick=()=>$('telegram-preview').classList.add('hidden');
$('post-select-all-approved').onclick=async()=>{try{const params=new URLSearchParams();const source=$('post-source').value,topic=$('post-topic').value,q=$('post-search').value.trim();if(source)params.set('source_id',source);if(topic)params.set('topic_id',topic);if(q)params.set('q',q);params.set('status','APPROVED');params.set('publication_state','ELIGIBLE');params.set('limit','500');let offset=0;const ids=[];while(true){params.set('offset',String(offset));const d=await request('/posts?'+params.toString());ids.push(...(d.items||[]).map(p=>p.post_id));offset+=(d.items||[]).length;if(offset>=Number(d.total||0)||(d.items||[]).length===0)break;}state.selectedPostIds=[...new Set(ids)];renderSelectionCount();loadPostBank();}catch(e){alert(e.message);}};
$('post-clear-selection').onclick=()=>{state.selectedPostIds=[];renderSelectionCount();loadPostBank();};
loadSchedules();loadUpcoming();loadCalendar();
loadPostSources().then(loadPostBank).catch(e=>$('post-bank-summary').textContent=e.message);
$('post-source').onchange=()=>{state.postOffset=0;loadPostTopics($('post-source').value);loadPostBank();};
$('post-topic').onchange=()=>{state.postOffset=0;loadPostBank();};
$('post-status').onchange=()=>{state.postOffset=0;loadPostBank();};$('post-publication-state').onchange=()=>{state.postOffset=0;loadPostBank();};
$('post-search').oninput=()=>{clearTimeout(state.postSearchTimer);state.postSearchTimer=setTimeout(()=>{state.postOffset=0;loadPostBank();},300);};
$('post-clear-filters').onclick=()=>{$('post-search').value='';$('post-source').value='';$('post-topic').innerHTML='<option value="">كل المحاور</option>';$('post-status').value='';$('post-publication-state').value='UNPUBLISHED';state.postOffset=0;loadPostBank();};
$('post-refresh').onclick=()=>loadPostBank();
$('post-prev').onclick=()=>{state.postOffset=Math.max(0,state.postOffset-50);loadPostBank();};
$('post-next').onclick=()=>{state.postOffset+=50;loadPostBank();};
$('post-editor-close').onclick=()=>$('post-editor').classList.add('hidden');
$('post-editor-save').onclick=savePost;$('post-editor-approve').onclick=()=>reviewPost('approve');$('post-editor-reject').onclick=()=>reviewPost('reject');$('post-bulk-approve').onclick=bulkApproveSelected;
async function hydrateSelectionFromUrl(){const raw=new URLSearchParams(window.location.search).get('selected_post_ids');if(!raw)return;const ids=[...new Set(raw.split(',').map(x=>x.trim()).filter(Boolean))];if(!ids.length)return;state.selectedPostIds=ids;try{const result=await filterSelectionForScheduling();if(!state.selectedPostIds.length){$('schedule-create-error').textContent='لم يبقَ في الاختيار أي منشور قابل للنشر.';return;}state.scheduleIdempotencyKey=window.crypto?.randomUUID?window.crypto.randomUUID():String(Date.now())+'-'+Math.random();renderSelectionCount();await renderScheduleSelection();$('schedule-create-panel').classList.remove('hidden');$('schedule-create-error').textContent='تم نقل '+state.selectedPostIds.length+' منشورًا قابلًا للنشر من مصنع المنشورات. راجع الترتيب والتوقيت ثم احفظ الخطة.';window.location.hash='scheduling-section';}catch(e){$('schedule-create-error').textContent='تعذر التحقق من قابلية النشر: '+e.message;}}
renderSelectionCount();
hydrateSelectionFromUrl().catch(e=>{$('schedule-create-error').textContent='تعذر استعادة الاختيار: '+e.message;});
loadSources().catch(e=>showError('تعذر تحميل المكتبة. '+e.message));
</script></body></html>'''
