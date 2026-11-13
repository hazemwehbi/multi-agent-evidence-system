import json
import subprocess
import sys


def test_cli_runs_in_fresh_process_without_credentials():
    result = subprocess.run(
        [sys.executable, "-m", "app.cli", "smoke"],
        capture_output=True, text=True, check=True, timeout=10,
    )
    report = json.loads(result.stdout)
    assert report["result"] == {"status": "ready"}
    assert report["model"]["provider"] == "offline"
    assert report["model"]["model"] == "deterministic-v1"
    assert report["execution_id"] and report["started_at"]
    assert result.stderr == ""


def test_workflow_cli_runs_in_fresh_process_without_credentials():
    result = subprocess.run(
        [sys.executable, "-m", "app.cli", "demo"],
        capture_output=True, text=True, check=True, timeout=10,
    )
    report = json.loads(result.stdout)
    assert report["run"]["model"]["provider"] == "offline"
    assert report["run"]["status"] == "succeeded"
    assert report["steps"] == 6
    assert report["result"]["decision"]["action"] == "publish_supported_findings"
    assert result.stderr == ""
