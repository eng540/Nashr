import type { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="workspace-hero">
      <div className="min-w-0">
        {eyebrow ? <p className="workspace-kicker">{eyebrow}</p> : null}
        <h2 className="text-2xl font-extrabold tracking-tight text-slate-900">{title}</h2>
        {description ? <p className="mt-1.5 max-w-2xl text-sm leading-7 text-slate-500">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function Card({ children, className, ...rest }: HTMLAttributes<HTMLElement>) {
  return (
    <section className={cx("rounded-2xl border border-slate-200/80 bg-white p-5 shadow-[0_1px_2px_rgba(15,23,42,0.05)]", className)} {...rest}>
      {children}
    </section>
  );
}

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost" | "success" | "sky";
const buttonVariants: Record<ButtonVariant, string> = {
  primary: "bg-brand-600 text-white hover:bg-brand-700 disabled:bg-brand-300",
  secondary: "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 disabled:text-slate-400",
  danger: "bg-rose-600 text-white hover:bg-rose-700 disabled:bg-rose-300",
  ghost: "text-slate-600 hover:bg-slate-100 disabled:text-slate-400",
  success: "bg-emerald-600 text-white hover:bg-emerald-700 disabled:bg-emerald-300",
  sky: "bg-sky-700 text-white hover:bg-sky-800 disabled:bg-sky-300",
};

export function Button({ variant = "primary", className, type = "button", ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button
      type={type}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-xl px-4 py-2 text-sm font-bold transition-colors disabled:cursor-not-allowed",
        buttonVariants[variant],
        className,
      )}
      {...rest}
    />
  );
}

type BadgeTone = "brand" | "slate" | "emerald" | "amber" | "rose" | "sky";
const badgeTones: Record<BadgeTone, string> = {
  brand: "bg-brand-50 text-brand-700 ring-brand-100",
  slate: "bg-slate-100 text-slate-600 ring-slate-200",
  emerald: "bg-emerald-50 text-emerald-700 ring-emerald-100",
  amber: "bg-amber-50 text-amber-800 ring-amber-100",
  rose: "bg-rose-50 text-rose-700 ring-rose-100",
  sky: "bg-sky-50 text-sky-700 ring-sky-100",
};

export function Badge({ tone = "slate", children }: { tone?: BadgeTone; children: ReactNode }) {
  return <span className={cx("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-bold ring-1 ring-inset", badgeTones[tone])}>{children}</span>;
}

export const inputClass = "w-full max-w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm transition-colors placeholder:text-slate-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100";

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx(inputClass, className)} {...rest} />;
}

export function Select({ className, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cx(inputClass, className)} {...rest} />;
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cx(inputClass, className)} {...rest} />;
}

export function Field({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <label className={cx("block text-sm font-bold text-slate-700", className)}>
      {label}
      <div className="mt-1.5 font-normal">{children}</div>
    </label>
  );
}

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50/60 p-8 text-center">
      <p className="text-sm font-bold text-slate-600">{title}</p>
      {description ? <p className="mt-1 text-xs leading-6 text-slate-400">{description}</p> : null}
    </div>
  );
}

export function StatusNote({ tone = "slate", children, role = "status" }: { tone?: BadgeTone; children: ReactNode; role?: "status" | "alert" }) {
  return <p role={role} className={cx("rounded-xl px-3 py-2 text-sm", badgeTones[tone], "ring-1 ring-inset")}>{children}</p>;
}
