from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.static import SPAStaticFiles


def make_client(tmp_path) -> TestClient:
    (tmp_path / "index.html").write_text("<html>index</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "a.js").write_text("console.log(1)")
    app = FastAPI()
    app.mount("/", SPAStaticFiles(directory=tmp_path, html=True), name="frontend")
    return TestClient(app)


def test_client_routes_fall_back_to_index(tmp_path):
    client = make_client(tmp_path)
    for path in ("/", "/postings/1", "/bookmarks"):
        r = client.get(path)
        assert r.status_code == 200 and r.text == "<html>index</html>", path


def test_files_and_api_are_not_rewritten(tmp_path):
    client = make_client(tmp_path)
    r = client.get("/assets/a.js")
    assert r.status_code == 200 and r.text == "console.log(1)"
    assert client.get("/assets/missing.js").status_code == 404
    assert client.get("/api/x").status_code == 404
    assert client.get("/api").status_code == 404
