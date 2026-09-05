# Engineering Findings

Empirical issues discovered while building RingGuard, and how they were
resolved. Kept public on purpose: a risk prototype that hides its own
failure modes is not credible.

## F1. Market-pool projection collapses the ecosystem into one blob

**Found (M5, demo scale).** Normal users draw device/card/IP usage from a
*shared market pool* (`privacy_level` < 1 by design). Raw connected
components over shared infrastructure therefore chained ~70 of 120 demo
users into a single candidate "ring" containing a quarter of the
ecosystem — useless for investigation, and it would swallow real rings.

**Fix.** Two layers:
1. The projection's fan-out cap treats heavily-shared resources as
   population-level infrastructure and excludes them.
2. Discovery partitions the *weighted* projection with Louvain modularity
   (`backend/detection/rings.py`) instead of raw components. Modularity
   separates dense coordination subgraphs (rings share device **and**
   card **and** IP, so pair weights are 4–6) from sparse background
   chains (a single shared device, weight 2).

## F2. A fixed fan-out cap silently severs real rings

**Found (M5, demo scale).** The original cap was absolute
(`MAX_SHARED_FANOUT = 6`). Planted demo rings have 8–9 members sharing a
farm device — i.e. the *device-farm signal itself* exceeded the cap and
was excluded as "public infrastructure". Result: 4 of 5 planted abuse
rings were not covered by any discovery candidate (recall 1/5), even
though the tiny-scale test suite was green. Classic scale-blind bug.

**Fix.** The cap now scales with the population:
`max(MAX_SHARED_FANOUT, ceil(0.25 * n_users))` (`FANOUT_POP_FRACTION`).
A device shared by 8 of 12 users is background; a device shared by 8 of
120 users is a textbook device farm. Both scale regimes are now covered
by regression tests (`backend/tests/test_m5_rings.py::TestDemoScale`).

## F3. Pattern classification must use coverage, not entity counts

**Found (M5, tiny scale).** `_primary_pattern` compared *counts* of
reachable devices vs IPs. A device-farm plant whose members also kept
personal devices misclassified as "payment-instrument sharing", because
raw device counts lost to IP counts — even though every member rode the
shared farm device.

**Fix.** Classification now uses *coverage*: the fraction of ring users
participating in a resource shared by ≥2 members. Coverage is also the
semantically correct reading of spec §6's signal hierarchy (shared IP =
weak, shared device = moderate, device + instrument = strong).

## Open observations (accepted for now)

- Family-card communities (hard negative) do not always surface as
  discovery candidates; they are conservative misses, not false
  positives. The M6 risk engine will still grade any user-level
  evidence they produce.
- Background communities of ~10–18 lightly-connected users still appear
  as candidates with mid structural scores (e.g. 0.65–0.79). Discovery
  is deliberately recall-oriented; separating them from abuse is the
  risk engine's job (temporal + behavioral + legitimate-sharing layers).
