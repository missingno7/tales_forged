# Replay architecture migration

The active DuckTales replay path is fully based on ReplayArtifactV2,
ReplaySession, EvidenceV3, stable Amiga semantic points, and explicit execution
plans. `ContinuationState` owns session cursors and point occurrences while the
Amiga machine snapshot owns future-affecting hardware and service state.

The historical input timeline was converted once into
`recovery/migration/cold5-input-schedule-v1.json`. That schedule has no replay
identity or verification authority; it is accepted only while recording a new
ArtifactV2. The resulting curated artifact, exact base snapshot, boundary
profile, evidence, plans, and detachment reports are the current tracked
architecture inputs.

Retired replay/evidence/Atlas envelopes are intentionally neither parsed nor
accepted by active launchers or the shared project control plane. They can be
recovered from repository history if an archaeology task needs them.
