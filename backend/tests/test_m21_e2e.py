"""M21 scripted end-to-end gate."""

from scripts.e2e_smoke import run_smoke


def test_generate_detect_serve_investigate_and_simulate():
    result = run_smoke(demo=False, require_frontend=False)
    assert result["top_ring_risk"] >= 0
    assert result["graph_nodes"] > 0
    assert result["history_points"] > 1
    assert result["simulated_alert"] is True
