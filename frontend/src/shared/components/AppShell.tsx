import type { ReactNode } from "react";
import { NavLink } from "react-router";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-5">
          <div>
            <p className="text-xs font-bold text-indigo-600">Nashr</p>
            <h1 className="text-xl font-bold">منصة الإنتاج والنشر</h1>
          </div>
          <nav className="flex gap-2 text-sm font-semibold">
            <NavLink to="/posts/workspace" className={({ isActive }) => `rounded-xl px-4 py-2 ${isActive ? "bg-indigo-600 text-white" : "bg-slate-100"}`}>
              مصنع المحتوى
            </NavLink>
            <NavLink to="/control" className={({ isActive }) => "rounded-xl px-4 py-2 " + (isActive ? "bg-indigo-600 text-white" : "bg-slate-100")}>
              التحكم
            </NavLink>
            <NavLink to="/publishing" className={({ isActive }) => `rounded-xl px-4 py-2 ${isActive ? "bg-indigo-600 text-white" : "bg-slate-100"}`}>
              النشر
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-8">{children}</main>
    </div>
  );
}
