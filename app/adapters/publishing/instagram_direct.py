"""Dormant Instagram Login publishing edge. Never creates a media grant.

Shares validated single-JPEG/Reel mechanics, but never Facebook credentials,
Page enumeration or Unified capability checks. No production routes import it.
"""
from datetime import datetime,timezone
from app.adapters.publishing.instagram import InstagramPublisher,InstagramProviderError
from app.application.instagram_direct_oauth import read_identity,DirectFailure,SCOPES

class InstagramDirectPublisher(InstagramPublisher):
    graph_base='https://graph.instagram.com/v27.0'

    async def verify_account(self,*,expected_username,app_scoped_id,scopes,expires_at):
        # Scope provenance and deadline come from the encrypted state-bound
        # OAuth exchange. Facebook debug_token is not used for Instagram tokens.
        if not isinstance(scopes,list) or not SCOPES.issubset(scopes):raise InstagramProviderError('INSTAGRAM_PERMISSION_REQUIRED')
        if not isinstance(expires_at,datetime) or expires_at.tzinfo is None or expires_at<=datetime.now(timezone.utc):raise InstagramProviderError('INSTAGRAM_RECONNECT_REQUIRED')
        try:account=await read_identity(self.client,self.token)
        except DirectFailure:raise InstagramProviderError('INSTAGRAM_READ_FAILED') from None
        if account!={'account_id':self.account_id,'username':expected_username,'app_scoped_id':app_scoped_id}:raise InstagramProviderError('INSTAGRAM_ACCOUNT_MISMATCH')
        return {**account,'token_type':'INSTAGRAM_USER','scopes':sorted(set(scopes)),'expires_at':int(expires_at.timestamp()),'execution_authorized':False}
