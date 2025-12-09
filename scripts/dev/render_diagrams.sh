#!/usr/bin/env bash
set -euo pipefail

# Small helper to render mermaid diagrams into the docs/diagrams/assets directory
# Requires `mmdc` (Mermaid CLI) to be installed and on PATH.

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
DIAGRAMS_DIR="$REPO_ROOT/docs/diagrams"
ASSETS_DIR="$DIAGRAMS_DIR/assets"

echo "Rendering Mermaid diagrams to SVG (requires mmdc)..."

if ! command -v mmdc >/dev/null 2>&1; then
  echo "WARNING: Mermaid CLI (mmdc) not found in PATH. Skipping .mmd -> .svg rendering step and continuing to SVG->raster conversion (if any SVGs exist)." >&2
  MMDC_PRESENT=false
else
  MMDC_PRESENT=true
fi

mkdir -p "$ASSETS_DIR"

PUPPETEER_BIN=$(command -v chromium || command -v chromium-browser || command -v google-chrome || true)
if [ -z "$PUPPETEER_BIN" ]; then
  echo "WARNING: no Chromium/Chrome executable found on PATH — mermaid-cli may still work if puppeteer is configured to download a bundle."
fi

if [ "$MMDC_PRESENT" = true ]; then
  for src in "$DIAGRAMS_DIR"/*.mmd; do
    base=$(basename "$src" .mmd)
    out="$ASSETS_DIR/${base}.svg"
    echo " - $src -> $out"
    if [ -n "$PUPPETEER_BIN" ]; then
      # Some distributions (snap) require running chromium with no-sandbox from non-privileged contexts
      PUPPETEER_EXECUTABLE_PATH="$PUPPETEER_BIN" PUPPETEER_ARGS="--no-sandbox --disable-setuid-sandbox" \
        mmdc -i "$src" -o "$out" || { echo "failed to render $src — continuing (will still attempt SVG->raster conversion)" >&2; continue; }
    else
      mmdc -i "$src" -o "$out" || { echo "failed to render $src — continuing (will still attempt SVG->raster conversion)" >&2; continue; }
    fi
  done
else
  echo "Skipping .mmd -> .svg steps because mmdc wasn't detected. Will convert existing SVG assets instead (if present)."
fi

echo "Done. SVG assets are in $ASSETS_DIR"

# --- raster conversion fallback -------------------------------------------------
echo "\nAttempting to create PNG/JPEG raster exports from SVG assets (preferred: system/conda tools)..."

# Detect a rasterizer: prefer rsvg-convert (librsvg), then magick/convert (ImageMagick)
if command -v rsvg-convert >/dev/null 2>&1; then
  RASTER="rsvg-convert"
elif command -v magick >/dev/null 2>&1; then
  RASTER="magick"
elif command -v convert >/dev/null 2>&1; then
  RASTER="convert"
else
  RASTER=""
fi

if [ -z "$RASTER" ]; then
  echo "WARNING: No rasterization tool found (rsvg-convert or ImageMagick). SVG->PNG/JPEG conversion skipped." >&2
  exit 0
fi

echo "Using rasterizer: $RASTER"

shopt -s nullglob
for svg in "$ASSETS_DIR"/*.svg; do
  base=$(basename "$svg" .svg)
  png="$ASSETS_DIR/${base}.png"
  jpg="$ASSETS_DIR/${base}.jpg"

  echo " - Converting $svg -> $png and $jpg"
  if [ "$RASTER" = "rsvg-convert" ]; then
    # rsvg-convert preserves transparency and can emit png/jpeg
    rsvg-convert -f png -o "$png" "$svg" || { echo "failed to render PNG for $svg" >&2; continue; }
    # For JPEG, fill background white since JPEG has no alpha; only if ImageMagick is available
    if command -v convert >/dev/null 2>&1; then
      rsvg-convert -f png "$svg" | convert png:- -background white -flatten "$jpg" || { echo "failed to render JPG for $svg" >&2; }
    elif command -v magick >/dev/null 2>&1; then
      rsvg-convert -f png "$svg" | magick png:- -background white -flatten "$jpg" || { echo "failed to render JPG for $svg" >&2; }
    else
      echo " - note: ImageMagick not available, skipping JPEG for $svg" >&2
    fi

  else
    # magick/convert can read SVG directly
    if [ "$RASTER" = "magick" ]; then
      magick "$svg" -background none "$png" || { echo "failed to render PNG for $svg" >&2; continue; }
      magick "$svg" -background white -flatten "$jpg" || { echo "failed to render JPG for $svg" >&2; continue; }
    else
      convert "$svg" -background none "$png" || { echo "failed to render PNG for $svg" >&2; continue; }
      convert "$svg" -background white -flatten "$jpg" || { echo "failed to render JPG for $svg" >&2; continue; }
    fi
  fi
done
shopt -u nullglob

echo "Raster exports written (when possible) to $ASSETS_DIR"
