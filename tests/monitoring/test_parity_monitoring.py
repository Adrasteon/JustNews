from pathlib import Path


def test_parity_alerts_and_dashboard_present():
    repo_root = Path(__file__).resolve().parents[2]
    alerts_file = repo_root / "docs" / "monitoring" / "parity-alerts.yml"
    assert alerts_file.exists(), f"Parity alert docs missing: {alerts_file}"
    content = alerts_file.read_text(encoding="utf-8")
    assert "ParityMismatchDetected" in content
    assert "ParityRepairFailures" in content
    # Also ensure the 'repairs required' alert is present (mismatches without observed repairs)
    assert "ParityRepairRequired" in content

    dashboard = repo_root / "monitoring" / "dashboards" / "generated" / "parity_dashboard.json"
    assert dashboard.exists(), f"Parity Grafana dashboard missing: {dashboard}"
