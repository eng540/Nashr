from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app


def test_public_exact_domain_proof(monkeypatch):
    monkeypatch.setenv("NASHR_AUTH_PASSWORD", "owner-test-only")
    app=create_app()
    proof=next((Path(__file__).resolve().parents[2]/"app"/"static").glob("tiktok*.txt"))
    client=TestClient(app)
    response=client.get("/"+proof.name)
    assert response.status_code==200
    assert response.content==proof.read_bytes().rstrip(b"\n")
    assert len(response.content)==68
    assert response.headers["content-type"].startswith("text/plain")
    assert client.get("/api/connections/tiktok").status_code==401
    assert client.get("/tiktok-unregistered.txt",follow_redirects=False).status_code in {401,303,404}


def test_public_exact_sandbox_proof_preserves_existing(monkeypatch):
    monkeypatch.setenv("NASHR_AUTH_PASSWORD", "owner-test-only")
    client=TestClient(create_app())
    root=Path(__file__).resolve().parents[2]/"app"/"static"
    for filename in ["tiktokePPmBzm3Ej1QWBVM7rVXy8eiIbCCGpJj.txt", "tiktokQDsoHAsAIEswE2q0vxreoi4iWCJbhDsS.txt"]:
        response=client.get("/"+filename)
        assert response.status_code==200
        assert response.content==(root/filename).read_bytes().rstrip(b"\n")
        assert len(response.content)==68
    assert client.get("/api/connections/tiktok").status_code==401
    assert client.get("/bank").status_code==401
