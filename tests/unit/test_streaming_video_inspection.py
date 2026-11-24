import hashlib
import io
from pathlib import Path
import pytest
from app.infrastructure.artifact_storage import S3ArtifactStorage,ArtifactStorageError

class Body(io.BytesIO):
    def __init__(self,data):super().__init__(data);self.requests=[]
    def read(self,n=-1):
        assert 0<n<=1024*1024
        self.requests.append(n);return super().read(n)
class Client:
    def __init__(self,data,declared=None):self.body=Body(data);self.declared=declared
    def get_object(self,**kw):return {'Body':self.body,**({'ContentLength':self.declared} if self.declared is not None else {})}

@pytest.mark.asyncio
async def test_download_is_chunked_hashed_private_and_cleaned():
    data=b'a'*(2*1024*1024+10);client=Client(data,len(data));paths=[]
    def inspect(path):
        paths.append(path);assert Path(path).stat().st_mode&0o077==0
        return Path(path).stat().st_size
    result,digest=await S3ArtifactStorage(client=client,bucket='test').inspect_local_file('s3://test/artifacts/video.mp4',inspect)
    assert result==len(data) and digest==hashlib.sha256(data).hexdigest()
    assert client.body.closed and len(client.body.requests)>2 and not Path(paths[0]).exists()

@pytest.mark.asyncio
@pytest.mark.parametrize('declared',[None,11])
async def test_declared_or_actual_overflow_never_runs_probe(declared):
    client=Client(b'x'*11,declared)
    with pytest.raises(ArtifactStorageError):
        await S3ArtifactStorage(client=client,bucket='test').inspect_local_file('s3://test/artifacts/video.mp4',lambda path:pytest.fail('probe must not run'),max_bytes=10)
    assert client.body.closed

@pytest.mark.asyncio
async def test_failed_probe_cleans_file_and_closes_body():
    client=Client(b'video');paths=[]
    def inspect(path):paths.append(path);raise ValueError('invalid media')
    with pytest.raises(ArtifactStorageError):await S3ArtifactStorage(client=client,bucket='test').inspect_local_file('s3://test/artifacts/video.mp4',inspect)
    assert client.body.closed and not Path(paths[0]).exists()


def test_real_video_with_large_sparse_free_box_can_be_probed_without_full_read(tmp_path):
    import shutil,subprocess,struct
    from app.domain.platform_media_probe import inspect_video_file
    if not shutil.which('ffmpeg'):pytest.skip('ffmpeg required')
    path=tmp_path/'large.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=blue:s=160x120:r=25','-t','3','-c:v','libx264','-an','-y',str(path)],check=True,timeout=15)
    with path.open('r+b') as f:
        f.seek(0,2);f.write(struct.pack('>I4s',60*1024*1024,b'free'));f.seek(60*1024*1024-9,1);f.write(b'0')
    info=inspect_video_file(str(path))
    assert info['size_bytes']>50*1024*1024 and info['width']==160
    assert info['inspection_input_limit_bytes']==300_000_000

@pytest.mark.asyncio
async def test_busy_worker_limit_does_not_download():
    from app.infrastructure.artifact_storage import _VIDEO_INSPECTION_SLOTS
    _VIDEO_INSPECTION_SLOTS.acquire();_VIDEO_INSPECTION_SLOTS.acquire()
    try:
        client=Client(b'video')
        with pytest.raises(ArtifactStorageError,match='busy'):
            await S3ArtifactStorage(client=client,bucket='test').inspect_local_file('s3://test/artifacts/video.mp4',lambda p:None)
        assert not client.body.requests
    finally:_VIDEO_INSPECTION_SLOTS.release();_VIDEO_INSPECTION_SLOTS.release()

@pytest.mark.asyncio
async def test_cancellation_does_not_orphan_open_temporary_file():
    import asyncio,threading
    client=Client(b'video');started=threading.Event();finish=threading.Event();cleaned=threading.Event();paths=[]
    def inspect(path):
        paths.append(path);started.set();finish.wait(2);return True
    task=asyncio.create_task(S3ArtifactStorage(client=client,bucket='test').inspect_local_file('s3://test/artifacts/video.mp4',inspect))
    await asyncio.to_thread(started.wait,2);assert started.is_set();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    finish.set()
    for _ in range(100):
        if not Path(paths[0]).exists() and client.body.closed:break
        await asyncio.sleep(.01)
    assert not Path(paths[0]).exists() and client.body.closed
