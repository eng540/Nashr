"""Redact credentials without breaking structured access-log formatters."""
import logging,re

def redact(message):
    message=re.sub(r'(api\.telegram\.org/bot)[^/\s]+',r'\1[REDACTED]',message)
    return re.sub(r'([?&](?:access_token|input_token|client_secret|code|state|upload_id)=)[^&\s"\']+',r'\1[REDACTED]',message)

class CredentialFilter(logging.Filter):
    def filter(self,record):
        # Uvicorn AccessFormatter unpacks its five arguments. Preserve that
        # structure, sanitizing only strings before either formatter sees it.
        if record.name=='uvicorn.access' and isinstance(record.args,tuple) and len(record.args)==5:
            record.args=tuple(redact(x) if isinstance(x,str) else x for x in record.args)
            if isinstance(record.msg,str):record.msg=redact(record.msg)
        else:
            record.msg=redact(record.getMessage());record.args=()
        return True

def install():
    for name in ('httpx','httpcore','uvicorn.access'):
        logging.getLogger(name).addFilter(CredentialFilter())
    logging.getLogger('httpcore').setLevel(logging.CRITICAL)
