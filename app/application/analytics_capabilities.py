"""Stored permission evidence only. No token access, provider I/O or mutations."""
from sqlalchemy import select
from app.infrastructure.database.models import (
    InstagramConnectionModel, InstagramDirectConnectionModel,
    InstagramPageConnectionModel, FacebookPageConnectionModel,
)

IG_SOURCE = 'https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/insights'
DIRECT_SOURCE = 'https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/insights'
SPECS = (
    ('instagram_unified', InstagramConnectionModel, 'username',
     ('instagram_basic', 'instagram_manage_insights'), 'stored_token_debug_scopes', IG_SOURCE),
    ('instagram_direct', InstagramDirectConnectionModel, 'username',
     ('instagram_business_basic', 'instagram_business_manage_insights'), 'stored_code_exchange_permissions', DIRECT_SOURCE),
    ('instagram_page', InstagramPageConnectionModel, 'username',
     ('instagram_basic', 'instagram_manage_insights', 'pages_read_engagement'), None, IG_SOURCE),
    # Page tasks are not OAuth scopes. Metric-specific requirements are not yet mapped.
    ('facebook_page', FacebookPageConnectionModel, 'page_name', (), 'stored_token_debug_scopes', None),
)


def report_binding(key, row, requirements, evidence_source, source_url):
    present = row is not None
    raw = row['scopes'] if present and 'scopes' in row else None
    # Strictly reject ambiguous/malformed stored evidence rather than infer grants.
    scopes = sorted(set(raw)) if isinstance(raw, list) and all(isinstance(s, str) for s in raw) else None
    known = scopes is not None and evidence_source is not None
    missing = sorted(set(requirements) - set(scopes)) if known and requirements else None
    return {
        'key': key,
        'saved_connection_present': present,
        'identity': row['identity'] if present else None,
        'enabled_locally': row['enabled'] if present else None,
        'connected_at': row['connected_at'].isoformat() if present and row['connected_at'] else None,
        'last_check_at': row['last_check_at'].isoformat() if present and row['last_check_at'] else None,
        'last_check_ok': row['last_check_ok'] if present else None,
        'stored_expires_at': row['token_expires_at'].isoformat() if present and row['token_expires_at'] else None,
        'granted_scopes_at_saved_evidence': scopes if known else None,
        'scope_evidence_source': evidence_source if known else None,
        # External config_id scopes cannot be recovered without provider evidence.
        'requested_scopes': None,
        'configured_scopes': None,
        'documented_core_scopes': list(requirements) if requirements else None,
        'core_source_url': source_url,
        'missing_from_saved_scope_evidence': missing,
        'scope_status': 'NO_SAVED_CONNECTION' if not present else
                        'REQUIREMENTS_NOT_MAPPED' if not requirements else
                        'GRANT_EVIDENCE_UNKNOWN' if not known else
                        'MISSING_FROM_SAVED_EVIDENCE' if missing else 'CORE_PRESENT_DEPENDENCIES_UNMAPPED',
        'dependency_mapping': 'INCOMPLETE',
        'permission_reference_url': 'https://developers.facebook.com/docs/permissions/',
        'app_access_review': 'UNKNOWN',
        'current_provider_validation': 'NOT_ATTEMPTED',
        'metrics_status': 'NOT_IMPLEMENTED',
        'audience_active_times': 'UNCONFIRMED_UNAVAILABLE',
    }


async def capabilities(session):
    bindings = []
    for key, model, identity, requirements, evidence_source, source in SPECS:
        columns = [getattr(model, identity).label('identity'), model.enabled,
                   model.connected_at, model.last_check_at, model.last_check_ok,
                   model.token_expires_at]
        if hasattr(model, 'scopes'):
            columns.append(model.scopes)
        # Never SELECT the model or its encrypted credential/config fields.
        row = (await session.execute(select(*columns).where(model.id == 1))).mappings().one_or_none()
        bindings.append(report_binding(key, row, requirements, evidence_source, source))
    return {'mode': 'STORED_EVIDENCE_ONLY', 'provider_requests': 0,
            'metrics_fetched': False, 'bindings': bindings}
