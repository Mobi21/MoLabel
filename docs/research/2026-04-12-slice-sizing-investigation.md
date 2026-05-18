# Slice Sizing Investigation

Date: 2026-04-12
Related: `docs/research/2026-04-12-molabel-improvement-spec.md` §7.4

## Question

What minimum safe slice sizes are available in the committed authority packs?

## Finding

The committed redistributable fixtures do not currently contain enough records
to satisfy the requested §6.5 floors.

Current committed source sizes:

- clinc150: 16
- banking77: 16
- goemotions: 12
- feverous: 6
- scifact: 8
- hatexplain: 8

Requested floors in the spec:

- clinc150 / banking77 / goemotions / hatexplain: 40 each
- feverous / scifact: 20 each

## Conclusion

§6.5 is blocked on fixture expansion, not on runner logic.

The benchmark program can add explicit stability/hard-slice selectors, but it
cannot honestly claim the requested larger sizes until larger
provenance-tracked slices are committed.

## Recommendation

1. Treat the currently committed fixtures as the maximum available redistributable
   slices for now.
2. Land any selector/schema work separately from slice-size claims.
3. Re-open §6.5 only when larger authority-pack slices are added to the repo.
