# Changelog

## 1.1.0 — fork improvements

- Package CLI, processing modules, utilities, JSON Schema and YAML presets in wheels; declare core and optional dependencies and use one version source.
- Validate manifests and effective settings; resolve project paths consistently; reject incomplete/duplicate plate mappings.
- Add manifest-driven planning, optional dry-run, explicit stage selection, streaming output and execution records.
- Propagate CellProfiler wrapper/batch and segmentation retry failures; constrain GPU concurrency and expose worker limits.
- Join image channels by well/site keys; reject missing and duplicated channels instead of aligning by row position.
- Make ingestion strict and replace SQLite results atomically; validate extra-channel join cardinality.
- Allow feature selection without normalization; move project-name-specific scientific rules into explicit configuration.
- Remove personal annotation paths, pin documented external fork revisions, and add migration guidance.
- Add regression tests, isolated wheel smoke checks, a CPU synthetic demo, GitHub Actions CI, contributor guidance, citation and issue/PR templates.

## 1.0.0 — 2026-10-14

Original public release by Fernanda Garcia Fossa: CellProfiler workflows, micro-sam prediction, ingestion and pycytominer profile processing.
