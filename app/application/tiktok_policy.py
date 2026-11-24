"""Offline policy assessment only. No OAuth, media URL, API or execution grant."""
SOURCES={
 'guidelines':'https://developers.tiktok.com/docs/en/content-sharing-guidelines',
 'upload':'https://developers.tiktok.com/docs/en/content-posting-api-reference-upload-video',
 'upload_start':'https://developers.tiktok.com/docs/en/content-posting-api-get-started-upload-content',
 'direct':'https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post',
 'creator':'https://developers.tiktok.com/docs/en/content-posting-api-reference-query-creator-info',
 'status':'https://developers.tiktok.com/docs/en/content-posting-api-reference-get-video-status',
 'transfer':'https://developers.tiktok.com/docs/en/content-posting-api-media-transfer-guide',
}

def requirements():
    return dict(
        reviewed_on='2026-11-24',execution_enabled=False,account_connected=False,
        upload_enabled=False,approval_recorded=False,
        modes=[dict(key='INBOX_DRAFT',label='رفع كمسودة إلى إشعارات TikTok',scope='video.upload',
            requirements=['تطبيق مقبول وصلاحية video.upload مع موافقة صاحب الحساب، لم تتحقق بعد.',
                'إذن صريح بنقل الفيديو نفسه قبل بدء الرفع، لا من المعاينة أو اعتماد المادة.',
                'يفتح صاحب الحساب إشعار TikTok ليكمل التحرير والنشر بنفسه؛ وصول الإشعار ليس نشراً.',
                'قد ينشئ صاحب الحساب أكثر من منشور من المسودة نفسها؛ لا نفترض منشوراً واحداً لكل عملية.',
                'تسمح المنصة بحد أقصى خمس مشاركات معلقة خلال24ساعة، وليس وعداً بإتاحة الحصة للحساب.']),
            dict(key='DIRECT_POST',label='نشر مباشر، قبول الاستخدام غير متحقق',scope='video.publish',
            requirements=['إرشادات Direct Post تستبعد أداة داخلية لرفع محتوى حسابات الشخص أو فريقه؛ شكل Nashr الخاص الحالي لا يثبت أهلية التدقيق.',
                'العميل غير المدقق يقتصر على حسابات خاصة ومشاهدة SELF_ONLY. لا نغيّر خصوصية حسابك لتجاوز القيد.',
                'تحتاج الواجهة بيانات حساب حديثة وخيار خصوصية صريحاً دون قيمة افتراضية، وإعدادات التفاعل والإفصاح التجاري وحقوق الموسيقى.',
                'لا موافقة نشر أو جدولة أو تشغيل مباشر من هذه المرحلة.'])],
        media_requirements=['وسائط خادم التطبيق تستخدم رابط سحب من نطاق أو مسار متحقق لدى TikTok. لا نكشف الوسيط من هذه الصفحة.',
            'FILE_UPLOAD مخصص لملف جهاز المستخدم وفق الإرشادات؛ ليس التفافاً على متطلبات وسائط الخادم.',
            'حالة الإرسال للإشعارات منفصلة عن اكتمال النشر وعن إتاحته للعامة. لا إعادة تلقائية بعد نتيجة إرسال مجهولة.'],
        sources=[dict(label=k,url=v) for k,v in SOURCES.items()])

def assess(*,mode,storage_origin='SERVER',app_audited=False,app_scope_approved=False,
           owner_granted_scope=False,transfer_consented=False,verified_url_prefix=False,
           selected_privacy=None,privacy_options=None,creator_private=None,
           current_creator_checked=False,intended_audience='INTERNAL'):
    """Caller-supplied facts remain assumptions, never external verification.

    This model intentionally cannot return an executable/ready state. It captures
    known policy blockers without inventing app acceptance or token capability.
    """
    if mode not in {'INBOX_DRAFT','DIRECT_POST'}:raise ValueError('Explicit posting mode required')
    if storage_origin not in {'SERVER','DEVICE'}:raise ValueError('Known media origin required')
    flags=[app_audited,app_scope_approved,owner_granted_scope,transfer_consented,verified_url_prefix,current_creator_checked]
    if any(type(x) is not bool for x in flags):raise ValueError('Explicit boolean policy facts required')
    if creator_private is not None and type(creator_private) is not bool:raise ValueError('Invalid creator privacy')
    if intended_audience not in {'INTERNAL','WIDE_AUDIENCE'}:raise ValueError('Unknown intended audience')
    reasons=[]
    if not app_scope_approved:reasons.append('APP_SCOPE_ACCEPTANCE_UNVERIFIED')
    if not owner_granted_scope:reasons.append('OWNER_SCOPE_GRANT_MISSING')
    if not transfer_consented:reasons.append('EXPLICIT_MEDIA_TRANSFER_CONSENT_MISSING')
    if storage_origin=='SERVER' and not verified_url_prefix:reasons.append('SERVER_MEDIA_VERIFIED_PULL_URL_REQUIRED')
    if mode=='DIRECT_POST':
        if intended_audience=='INTERNAL':reasons.append('INTERNAL_UTILITY_EXCLUDED_BY_DIRECT_POST_GUIDELINES')
        if not current_creator_checked:reasons.append('FRESH_CREATOR_INFORMATION_REQUIRED')
        if not isinstance(privacy_options,list) or not privacy_options or not all(isinstance(x,str) for x in privacy_options) or selected_privacy not in privacy_options:reasons.append('EXPLICIT_AVAILABLE_PRIVACY_SELECTION_REQUIRED')
        if not app_audited and (selected_privacy!='SELF_ONLY' or creator_private is not True):reasons.append('UNAUDITED_REQUIRES_PRIVATE_CREATOR_AND_SELF_ONLY')
    return dict(mode=mode,scope='video.upload' if mode=='INBOX_DRAFT' else 'video.publish',
        transmission='PULL_FROM_URL' if storage_origin=='SERVER' else 'FILE_UPLOAD',
        blockers=reasons,external_facts_verified=False,execution_enabled=False,
        upload_enabled=False,approval_recorded=False,
        status='POLICY_BLOCKED' if reasons else 'POLICY_INPUTS_RECORDED_NOT_EXECUTABLE',
        sources=list(SOURCES.values()))
