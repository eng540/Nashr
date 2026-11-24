import { useState, type ReactNode } from "react";
import { NavLink } from "react-router";

const navItems = [
  { to: "/connections", label: "الحسابات والاتصالات" },
  { to: "/sources/library", label: "المصادر" },
  { to: "/production", label: "الإنتاج" },
  { to: "/bank", label: "بنك المحتوى" },
  { to: "/publishing", label: "النشر" },
  { to: "/control", label: "إعدادات التوليد" },
];

function navClass({ isActive }: { isActive: boolean }) {
  return [
    "rounded-xl px-3.5 py-2 text-sm font-bold transition-colors",
    isActive ? "bg-brand-600 text-white shadow-sm" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
  ].join(" ");
}

export function AppShell({ children }: { children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <div className="flex min-h-screen flex-col text-slate-900">
      <header className="sticky top-0 z-40 border-b border-slate-200/70 bg-white/85 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-3">
          <NavLink to="/publishing" className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600 text-lg font-extrabold text-white shadow-sm">ن</span>
            <span className="leading-tight">
              <span className="block text-[11px] font-bold text-brand-600">Nashr · نشر</span>
              <span className="block text-sm font-extrabold text-slate-900">منصة الإنتاج والنشر</span>
            </span>
          </NavLink>
          <nav className="hidden items-center gap-1 md:flex" aria-label="التنقل الرئيسي">
            {navItems.map((item) => <NavLink key={item.to} to={item.to} className={navClass}>{item.label}</NavLink>)}
          </nav>
          <button
            type="button"
            className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-bold text-slate-700 md:hidden"
            aria-expanded={menuOpen}
            aria-label="قائمة التنقل"
            onClick={() => setMenuOpen((open) => !open)}
          >
            ☰ القائمة
          </button>
        </div>
        {menuOpen ? (
          <nav className="border-t border-slate-200/70 bg-white px-4 py-2 md:hidden" aria-label="التنقل الرئيسي للجوال">
            <div className="flex flex-col gap-1 pb-2">
              {navItems.map((item) => (
                <NavLink key={item.to} to={item.to} className={navClass} onClick={() => setMenuOpen(false)}>{item.label}</NavLink>
              ))}
            </div>
          </nav>
        ) : null}
      </header>
      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8">{children}</main>
      <footer className="border-t border-slate-200/70 bg-white/60">
        <div className="mx-auto max-w-7xl px-4 py-4 text-center text-xs text-slate-400">
          نشر — مساحة عمل داخلية لإنتاج المحتوى ومراجعته واعتماده. لا يُنشر أي محتوى خارجيًا دون اعتماد يدوي.
        </div>
      </footer>
    </div>
  );
}
