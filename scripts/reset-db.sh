#!/usr/bin/env bash
# Drop all game data and re-run migrations + seed.
# Use when you want a clean slate without nuking the Docker volume.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== GamePrexDef DB Reset ==="
echo "WARNING: This will delete all game sessions and platform data."
read -rp "Continue? [y/N] " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

# Truncate all game-specific tables (preserves platform_types)
docker compose exec postgres psql -U gameprex -d gameprexdef -c "
  TRUNCATE TABLE intel_tracks, resource_states, facilities, missions, task_forces, platforms, game_sessions CASCADE;
"

# Re-seed platform types
echo "Re-seeding platform types..."
cd "$REPO_ROOT/db"
DATABASE_URL="postgresql://gameprex:gameprex_dev@localhost:5432/gameprexdef" \
  python seeds/seed_platforms.py

echo "Reset complete. All game data cleared, platform types restored."
