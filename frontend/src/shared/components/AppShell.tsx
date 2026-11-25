import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router";
const navItems=[
 {to:'/bank',label:'بنك المحتوى',icon:'▤',group:'مساحة العمل'},
 {to:'/publishing',label:'النشر',icon:'↗',group:'مساحة العمل'},
 {to:'/connections',label:'الحسابات والاتصالات',icon:'◎',group:'مساحة العمل'},
 {to:'/sources/library',label:'المصادر',icon:'▥',group:'الإنتاج'},
 {to:'/production',label:'الإنتاج',icon:'◇',group:'الإنتاج'},
 {to:'/control',label:'إعدادات التوليد المتقدمة',icon:'⚙',group:'الإنتاج'},
];
const navClass=({isActive}:{isActive:boolean})=>`app-nav-link ${isActive?'is-active':''}`;
export function AppShell({children}:{children:ReactNode}){
 const location=useLocation();
 const journey=[{to:"/sources/library",label:"1.المصادر"},{to:"/production",label:"2.الإنتاج"},{to:"/bank",label:"3.المراجعة والوجهات"},{to:"/publishing",label:"4.الجدولة والنتائج"}];
 const [menuOpen,setMenuOpen]=useState(false);
 const mainRef=useRef<HTMLElement>(null);
 const routeLabel=navItems.find(i=>i.to===location.pathname)?.label??'مساحة العمل';
 useEffect(()=>{setMenuOpen(false);document.title=routeLabel+' | نشر';},[location.pathname,routeLabel]);
 useEffect(()=>{if(!menuOpen)return;const close=(e:KeyboardEvent)=>{if(e.key==='Escape'){setMenuOpen(false);document.getElementById('navigation-toggle')?.focus();}};document.addEventListener('keydown',close);return()=>document.removeEventListener('keydown',close);},[menuOpen]);
 const brand=<NavLink to="/bank" className="app-brand"><span className="app-brand-mark">ن</span><span><strong>نشر <span>Nashr</span></strong><small>من المحتوى إلى النشر</small></span></NavLink>;
 return <div className="app-frame"><a className="app-skip" href="#main-content" onClick={()=>mainRef.current?.focus()}>تجاوز إلى المحتوى</a>
 <aside className="app-sidebar"><div className="app-sidebar-brand">{brand}</div><nav aria-label="التنقل الرئيسي">{['مساحة العمل','الإنتاج'].map(group=><div key={group} className="app-nav-group"><p>{group}</p>{navItems.filter(i=>i.group===group).map(i=><NavLink key={i.to} to={i.to} className={navClass}><span aria-hidden="true">{i.icon}</span>{i.label}</NavLink>)}</div>)}</nav><div className="app-sidebar-note"><span className="status-dot"/>مساحة عمل خاصة<small>المراجعة أولاً. النشر بقرارك.</small></div></aside>
 <div className="app-main-column"><header className="app-topbar"><div className="app-mobile-brand">{brand}</div><span className="app-desktop-context">مساحة العمل <span>/</span> {routeLabel}</span><span className="app-topbar-safety"><span className="status-dot"/>لا نشر تلقائي من التصفح</span><button type="button" id="navigation-toggle" className="app-menu-button" aria-controls="mobile-navigation" aria-expanded={menuOpen} aria-label="قائمة التنقل" onClick={()=>setMenuOpen(v=>!v)}>☰ القائمة</button></header>
 {menuOpen?<nav id="mobile-navigation" className="app-mobile-nav" aria-label="التنقل الرئيسي للجوال">{navItems.map(i=><NavLink key={i.to} to={i.to} className={navClass} onClick={()=>setMenuOpen(false)}>{i.label}</NavLink>)}</nav>:null}
 <main id="main-content" tabIndex={-1} ref={mainRef} className="app-main"><nav aria-label="رحلة المحتوى" className="service-journey">{journey.map(step=><NavLink key={step.to} to={step.to} aria-current={location.pathname===step.to?"step":undefined} className={location.pathname===step.to?"journey-current":""}>{step.label}</NavLink>)}<p>ملف جاهز؟ ابدأ من بنك المحتوى. كتاب PDF؟ ابدأ من المصادر. الاعتماد واختيار المنصات لا يرسلان شيئاً.</p></nav>{children}</main><footer className="app-footer">نشر · المحتوى الأصلي محفوظ، والاعتماد لا يعني النشر.</footer></div></div>;
}
