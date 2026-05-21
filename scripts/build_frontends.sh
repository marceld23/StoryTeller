#!/usr/bin/env bash
# Build both SvelteKit frontends as static SPAs into apps/*/frontend/build/.
# The FastAPI backends (storyteller-web-admin :8080, storyteller-web-ui :8090)
# serve those files directly, so there is no Node runtime in production.
#
# Prerequisites: Node 20 + corepack (yarn 4.x).  apt: sudo apt-get install -y nodejs
# Re-run after pulling frontend changes, then restart the two web services.
set -euo pipefail
cd "$(dirname "$0")/.."

command -v corepack >/dev/null || { echo "corepack/Node fehlt: sudo apt-get install -y nodejs" >&2; exit 1; }

for d in apps/web-ui/frontend apps/web-admin/frontend; do
  echo "=== building $d ==="
  ( cd "$d" && corepack yarn install && corepack yarn build )
done

echo
echo "fertig. Dienste neu starten, damit die neuen Builds ausgeliefert werden:"
echo "  sudo systemctl restart storyteller-admin storyteller-web-ui"
