#!/usr/bin/env bash
# Crea o actualiza los labels del AI Dev Team en un repo.
# Uso: scripts/sync-labels.sh maxiar-org/<repo>
set -euo pipefail
repo="${1:?Uso: $0 <org/repo>}"
labels_file="$(cd "$(dirname "$0")/.." && pwd)/github/labels.txt"
while IFS='|' read -r name color description; do
  [[ -z "$name" || "$name" == \#* ]] && continue
  gh label create "$name" --repo "$repo" --color "$color" --description "$description" --force
done < "$labels_file"
