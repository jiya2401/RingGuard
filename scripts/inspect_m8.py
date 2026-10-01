"""
Demo-scale M8 inspection: run the emerging-risk engine on the demo
ecosystem and print the report for the planted emerging ring (H).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.data.config import demo_config
from backend.data.generator import build_ecosystem
from backend.detection.rings import discover_rings
from backend.graph.builder import build_graph
from backend.risk.engine import score_rings
from backend.risk.emerging import DAY_S, emerging_report, graph_t0

eco = build_ecosystem(demo_config(), seed=42)
G = build_graph(eco)
rings = score_rings(discover_rings(G), G)

h_plants = [p for p in eco.plants if p.archetype == "H"]
h_users = set(h_plants[0].users) if h_plants else set()
tracked = [r for r in rings if h_users & set(r.users)]
print(f"demo rings: {len(rings)}, H-ring candidate(s): {[r.ring_id for r in tracked]}")

t0 = graph_t0(G)
cps = [t0 + d * DAY_S for d in range(2, 31, 2)]
report = emerging_report(G, cps)
print(f"tracked rings: {report['n_tracked']}")
for entry in report["rings"]:
    if h_users <= set(entry["users"]):
        print(f"\n{entry['ring_id']}  primary={entry['primary_pattern']}")
        print(f"  risk: {entry['first_risk']} -> {entry['final_risk']}  "
              f"rise={entry['rise']}  detected_day={entry['detected_day']}  "
              f"lead_days={entry['lead_days']}")
        print(f"  trajectory days: {[p['day'] for p in entry['history']]}")
        print(f"  trajectory risk: {[p['risk'] for p in entry['history']]}")
        for point in entry["history"]:
            for change in point["what_changed"]:
                print(f"  day {point['day']}: {change}")
