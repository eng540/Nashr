"""Snap Public Profile read-only identity edge, not an account connector.

No OAuth exchange, profile write, upload or publish operation is implemented.
Calling requires an independently authorized allowlisted app and owner token.
"""
from uuid import UUID
import httpx

GET_STARTED = 'https://developers.snap.com/marketing-api/Public-Profile-API/GetStarted'
PROFILES = 'https://developers.snap.com/marketing-api/Public-Profile-API/Profiles'
IDENTITY_URL = 'https://businessapi.snapchat.com/v1/public_profiles/my_profile'
REQUIREMENTS = (
    'الموصل غير منفذ بعد. مسار Public Profile API يتطلب تطبيق OAuth من حساب '
    'Business وإدراجه في قائمة السماح لدى Snap، ثم إذن مالك الملف العام بصلاحية '
    'snapchat-profile-api. ربط Login Kit أو وجود اسم مستخدم لا يثبت أهلية هذا '
    'المسار. لا نطلب إذناً أو ننشئ حساباً أو نرفع أو ننشر من هنا.'
)


class SnapchatIdentityError(ValueError):
    pass


def profile_identity(data, expected_profile_id=None):
    try:
        if not isinstance(data, dict) or data.get('request_status') != 'SUCCESS':
            raise ValueError()
        profile = data['public_profile']
        if not isinstance(profile, dict):
            raise ValueError()
        profile_id = str(UUID(profile['id']))
        if expected_profile_id is not None and profile_id != str(UUID(expected_profile_id)):
            raise ValueError()
        name, username = profile['display_name'], profile['snap_user_name']
        if not isinstance(name, str) or not name.strip() or len(name) > 500:
            raise ValueError()
        if not isinstance(username, str) or not username.strip() or len(username) > 100:
            raise ValueError()
        # Deliberately exclude phone, email, address, organization and media URLs.
        return {'profile_id': profile_id, 'display_name': name, 'username': username}
    except (KeyError, ValueError, TypeError, AttributeError):
        raise SnapchatIdentityError('PROFILE_IDENTITY') from None


async def identity(client, token, expected_profile_id=None):
    if not isinstance(token, str) or not 1 <= len(token) <= 16000 or any(c.isspace() for c in token):
        raise SnapchatIdentityError('ACCESS_TOKEN')
    try:
        response = await client.get(IDENTITY_URL, headers={'Authorization': 'Bearer ' + token},
                                    follow_redirects=False, timeout=15)
        if response.status_code != 200:
            raise ValueError()
        return profile_identity(response.json(), expected_profile_id)
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        # Provider errors may include identifiers or credentials. Do not echo.
        raise SnapchatIdentityError('IDENTITY_CHECK') from None
