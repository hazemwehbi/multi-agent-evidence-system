import re
import time

from fastapi.testclient import TestClient

from app.web import create_app


def test_upload_status_conflict_and_source_navigation(tmp_path):
    db = tmp_path / "web.sqlite"
    with TestClient(create_app(db)) as client:
        assert 'enctype="multipart/form-data"' in client.get("/").text
        response = client.post("/runs", data={"question": "Pilot budget"}, files=[
            ("files", ("one.txt", b"Pilot budget is 20.", "text/plain")),
            ("files", ("two.md", b"# Notes\n\nPilot budget is 24.\n\n<script>bad()</script>", "text/markdown")),
        ], follow_redirects=False)
        assert response.status_code == 303
        location = response.headers["location"]
        for _ in range(100):
            report = client.get(f"/api{location}").json()
            if "run" in report:
                break
            assert report["status"] == "running"
            time.sleep(0.02)
        assert report["run"]["status"] == "partial"
        decision = report["result"]["decision"]
        assert decision["abstained"]
        assert len(decision["considered"]) == 2
        assert {item["verification"]["assessment"]["label"] for item in decision["considered"]} == {"CONFLICTING"}
        assert not report["result"]["synthesis"]["finding_claim_ids"]
        page = client.get(location)
        assert "Decision record" in page.text and "Execution trace" in page.text
        assert "CONFLICTING" in page.text and "Contradicting" in page.text
        links = re.findall(r'href="([^"]+/evidence/[^"]+)"', page.text)
        originals = [client.get(link).text for link in set(links)]
        assert any("<mark>Pilot budget is 24." in text and "&lt;script&gt;" in text for text in originals)
        assert client.get(f"{location}/evidence/other/missing").status_code == 404
        rejected = client.post("/runs", data={"question": "Budget"}, files={
            "files": ("invalid.pdf", b"not a supported document"),
        })
        assert rejected.status_code == 400
    with TestClient(create_app(db)) as restarted:
        assert restarted.get(f"/api{location}").json() == report
