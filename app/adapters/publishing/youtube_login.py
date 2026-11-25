"""Read-only Google OAuth edge. No upload scope or content endpoints."""
import httpx
from app.adapters.publishing.youtube import CHANNEL

SCOPE = 'https://www.googleapis.com/auth/youtube.readonly'
TOKEN = 'https://oauth2.googleapis.com/token'

class YouTubeLoginError(ValueError):
    pass

def tokens(body, *, previous_refresh=None):
    if not isinstance(body, dict) or body.get('error') or body.get('token_type', '').lower() != 'bearer':
        raise YouTubeLoginError('YOUTUBE_TOKEN_INVALID')
    if set(str(body.get('scope', SCOPE if previous_refresh else '')).split()) != {SCOPE}:
        raise YouTubeLoginError('YOUTUBE_SCOPE_MISMATCH')
    access = body.get('access_token')
    refresh = body.get('refresh_token', previous_refresh)
    if any(not isinstance(x, str) or not 1 <= len(x) <= 16000 for x in [access, refresh]):
        raise YouTubeLoginError('YOUTUBE_TOKEN_INVALID')
    if type(body.get('expires_in')) is not int or not 0 < body['expires_in'] <= 86400:
        raise YouTubeLoginError('YOUTUBE_TOKEN_EXPIRY')
    expiry = body.get('refresh_token_expires_in')
    if expiry is not None and (type(expiry) is not int or not 0 < expiry <= 366 * 86400):
        raise YouTubeLoginError('YOUTUBE_REFRESH_EXPIRY')
    return dict(access_token=access, refresh_token=refresh, expires_in=body['expires_in'],
                refresh_expires_in=expiry, scope=SCOPE, token_type='Bearer')

async def token_request(client, config, values, *, previous_refresh=None):
    try:
        r = await client.post(TOKEN, data={**values, 'client_id': config['client_id'], 'client_secret': config['client_secret']})
        if r.status_code != 200:
            raise ValueError()
        return tokens(r.json(), previous_refresh=previous_refresh)
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        raise YouTubeLoginError('YOUTUBE_RECONNECT_REQUIRED') from None

async def exchange(client, config, code):
    return await token_request(client, config, dict(grant_type='authorization_code', code=code, redirect_uri=config['redirect_uri']))

async def refresh(client, config, refresh_token):
    return await token_request(client, config, dict(grant_type='refresh_token', refresh_token=refresh_token), previous_refresh=refresh_token)

async def channels(client, access_token):
    """Complete bounded enumeration, never accept a partial page as identity proof."""
    try:
        r = await client.get('https://www.googleapis.com/youtube/v3/channels', params={'part': 'id,snippet', 'mine': 'true', 'maxResults': 50}, headers={'Authorization': 'Bearer ' + access_token})
        b = r.json()
        rows = b.get('items')
        if r.status_code != 200 or b.get('error') or not isinstance(rows, list) or len(rows) > 50 or b.get('nextPageToken'):
            raise ValueError()
        out = []
        for item in rows:
            cid, title = item.get('id'), item.get('snippet', {}).get('title')
            if not isinstance(cid, str) or not CHANNEL.fullmatch(cid) or not isinstance(title, str) or not 1 <= len(title) <= 500 or any(x['channel_id'] == cid for x in out):
                raise ValueError()
            out.append({'channel_id': cid, 'title': title})
        if not out:
            raise ValueError()
        return out
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        raise YouTubeLoginError('YOUTUBE_CHANNEL_CHECK_FAILED') from None
