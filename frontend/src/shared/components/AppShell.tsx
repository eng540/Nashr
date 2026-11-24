import { useState, type ReactNode } from "react";
import { NavLink } from "react-router";
const navItems=[
 {to:'/bank',label:'بنك المحتوى',icon:'▤',group:'مساحة العمل'},
 {to:'/publishing',label:'النشر',icon:'↗',group:'مساحة العمل'},
 {to:'/connections',label:'الحسابات والاتصالات',icon:'◎',group:'مساحة العمل'},
 {to:'/sources/library',label:'المصادر',icon:'▥',group:'الإنتاج'},
 {to:'/production',label:'الإنتاج',icon:'◇',group:'الإنتاج'},
 {to:'/control',label:'إعدادات التوليد',icon:'⚙',group:'الإنتاج'},
];
const navClass=({isActive}:{isActive:boolean})=>`app-nav-link ${isActive?'is-active':''}`;
export function AppShell({children}:{children:ReactNode}){
 const [menuOpen,setMenuOpen]=useState(false);
 const brand=<NavLink to="/bank" className="app-brand"><span className="app-brand-mark">ن</span><span><strong>نشر <span>Nashr</span></strong><small>من المحتوى إلى النشر</small></span></NavLink>;
 return <div className="app-frame">
 <aside className="app-sidebar"><div className="app-sidebar-brand">{brand}</div><nav aria-label="التنقل الرئيسي">{['مساحة العمل','الإنتاج'].map(group=><div key={group} className="app-nav-group"><p>{group}</p>{navItems.filter(i=>i.group===group).map(i=><NavLink key={i.to} to={i.to} className={navClass}><span aria-hidden="true">{i.icon}</span>{i.label}</NavLink>)}</div>)}</nav><div className="app-sidebar-note"><span className="status-dot"/>مساحة عمل خاصة<small>المراجعة أولاً. النشر بقرارك.</small></div></aside>
 <div className="app-main-column"><header className="app-topbar"><div className="app-mobile-brand">{brand}</div><span className="app-desktop-context">مساحة العمل <span>/</span> إدارة المحتوى والنشر</span><span className="app-topbar-safety"><span className="status-dot"/>لا نشر تلقائي من التصفح</span><button type="button" className="app-menu-button" aria-expanded={menuOpen} aria-label="قائمة التنقل" onClick={()=>setMenuOpen(v=>!v)}>☰ القائمة</button></header>
 {menuOpen?<nav className="app-mobile-nav" aria-label="التنقل الرئيسي للجوال">{navItems.map(i=><NavLink key={i.to} to={i.to} className={navClass} onClick={()=>setMenuOpen(false)}>{i.label}</NavLink>)}</nav>:null}
 <main className="app-main">{children}</main><footer className="app-footer">نشر · المحتوى الأصلي محفوظ، والاعتماد لا يعني النشر.</footer></div></div>;
}
