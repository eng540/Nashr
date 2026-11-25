import {lazy,Suspense} from 'react';
import { Routes, Route, Navigate } from 'react-router';
import {PageLoadBoundary} from '../shared/components/PageLoadBoundary';
import { AppShell } from '../shared/components/AppShell';
const PublishingPage=lazy(()=>import('../features/publishing/PublishingPage').then(m=>({default:m.PublishingPage})));
const PostBankPage=lazy(()=>import('../features/post-bank/PostBankPage').then(m=>({default:m.PostBankPage})));
const ControlPlanePage=lazy(()=>import('../features/control-plane/ControlPlanePage').then(m=>({default:m.ControlPlanePage})));
const SourcesPage=lazy(()=>import('../features/sources/SourcesPage').then(m=>({default:m.SourcesPage})));
const ConnectionsPage=lazy(()=>import('../features/publishing/ConnectionsPage').then(m=>({default:m.ConnectionsPage})));
export function App(){return <AppShell><PageLoadBoundary><Suspense fallback={<section role="status" aria-live="polite" className="workspace-surface p-6"><h2 className="font-bold">جارٍ تجهيز مساحة العمل</h2><p>نحمّل الصفحة المطلوبة فقط. لم تُنفّذ أي عملية نشر.</p></section>}><Routes>
<Route path="/connections" element={<ConnectionsPage/>}/><Route path="/control" element={<ControlPlanePage/>}/><Route path="/publishing" element={<PublishingPage/>}/><Route path="/sources/library" element={<SourcesPage/>}/><Route path="/production" element={<PostBankPage initialView="production"/>}/><Route path="/bank" element={<PostBankPage initialView="review"/>}/><Route path="/posts/workspace" element={<PostBankPage/>}/><Route path="*" element={<Navigate to="/publishing" replace/>}/>
</Routes></Suspense></PageLoadBoundary></AppShell>;}
