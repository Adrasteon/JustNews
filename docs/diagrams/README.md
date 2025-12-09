# JustNews Diagrams

This folder contains a set of focused C4 diagrams that represent the JustNews agent architecture. Each diagram is intentionally scoped to reduce cross-edge clutter and make relationships easier to reason about.

Files
- `justnews_core_infra.mmd` — Core infrastructure: `mcp_bus`, `auth`, `balancer`, `gpu_orch`.
- `justnews_ingestion_pipeline.mmd` — Ingestion stage: `scout`, `c4ai`, `crawler`, `journalist`, `memory`.
- `justnews_analysis_hitl.mmd` — Analysis & HITL chain: `synthesizer`, `fact_checker`, `analyst`, `critic`, `hitl`, `chief_editor`.
- `justnews_storage_dashboard.mmd` — Storage & access: `memory`, `archive`, `dashboard`, `analytics`.
- `containers/crawler_container.mmd` — Container-level view for `crawler` showing internal subsystems.
- `containers/memory_container.mmd` — Container-level view for `memory` showing internal components: MariaDB, Chroma, embedding cache, vector engine.

Assets
- `assets/system_overview.svg` — visual, high-level overview diagram for the entire pipeline (recommended for README and architecture docs)
- `assets/orchestrator_flow.svg` — focused diagram showing orchestrator job submission → persistence → Redis stream → worker leasing → DLQ path

Mermaid sources
- `system_overview.mmd` — mermaid source for the high-level pipeline overview (renders to `assets/system_overview.svg`)
- `orchestrator_flow.mmd` — mermaid source for the orchestrator lifecycle (renders to `assets/orchestrator_flow.svg`)

Rendering
- Use Mermaid CLI (mmdc) to render the .mmd files to SVG. There is a helper script: `scripts/dev/render_diagrams.sh`.

Conda-friendly rendering / raster fallbacks
- The helper script now prefers system / conda-provided tools and will attempt two phases:
  1. Render mermaid `.mmd` -> `.svg` using `mmdc` (Mermaid CLI) if available.
  2. Convert any `.svg` files in `docs/diagrams/assets/` to raster images (PNG and JPEG) using system tools — no pip-required Python packages are necessary.

Recommended packages (conda-forge)
- Install librsvg (provides `rsvg-convert`) and/or ImageMagick via conda-forge to enable raster exports without pip:

```bash
# activate your conda env first
conda activate your-env-name
conda install -c conda-forge librsvg imagemagick
```

Notes
- `rsvg-convert` (librsvg) is preferred for clean SVG -> PNG rendering. If ImageMagick (`magick`/`convert`) is available the script will also produce JPEGs and provide better control over background flattening.
- We avoid pip here by preferring conda and system packages; if you must install Mermaid CLI you can install it globally with npm (there is no well-maintained conda package for `mmdc` at the time of writing).

Example:
```bash
# render all diagrams to docs/diagrams/assets
scripts/dev/render_diagrams.sh

# or render a single file via mmdc directly
mmdc -i docs/diagrams/system_overview.mmd -o docs/diagrams/assets/system_overview.svg

# The helper will also attempt to convert any SVG assets into PNG/JPEG images when system converters
# (librsvg/ImageMagick) are present. This avoids pip installs and works well within conda-based setups.
```

Why split into multiple diagrams
- The system is heavily interconnected; a single context diagram is too dense to read. Splitting improves readability and helps focus discussions on specific parts of the pipeline.

Styling & Improvements
- Relations are color-coded by domain (Green = storage, Blue = ingestion/control, Purple = analysis) to make lines visually thicker and more color-contrasting. No direct 'weight' property is supported in the C4 mermaid syntax, so color and offset are used to increase visibility.

Usage
- Use a Mermaid live editor or GitHub’s Mermaid rendering (where available) to preview `*.mmd` files.
- If you’d like me to also export PNG/SVG assets or add these diagrams to repo-as-docs, I can add an `assets/` directory with rendered images and link them from README.
- The repository already contains rendered SVG assets in `docs/diagrams/assets/` and those are linked from the canonical `docs/TECHNICAL_ARCHITECTURE.md`.

Next steps
- I can:  
  - Expand container-level diagrams to cover additional heavy agents (e.g., `synthesizer`, `analyst`, `fact_checker`).  
  - Add a single “overview” diagram that links the per-scope diagrams as a single flow with minimal connecting edges for context.  
  - Add a script to generate fallback PNGs using Mermaid CLI or GitHub Actions.