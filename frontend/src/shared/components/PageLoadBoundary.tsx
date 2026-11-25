import {Component,type ReactNode} from 'react';
export class PageLoadBoundary extends Component<{children:ReactNode},{failed:boolean}>{
 state={failed:false};
 static getDerivedStateFromError(){return {failed:true};}
 render(){if(this.state.failed)return <section role="alert" className="service-alert"><h2 className="font-bold">تعذر تحميل مساحة العمل</h2><p>قد يكون الاتصال انقطع أو وصل تحديث جديد. أعد تحميل الصفحة لقراءة الحالة الحالية قبل تكرار أي إجراء. إعادة التحميل لا تعيد إرسال منشور.</p><button type="button" onClick={()=>window.location.reload()}>إعادة تحميل الصفحة</button></section>;return this.props.children;}
}
