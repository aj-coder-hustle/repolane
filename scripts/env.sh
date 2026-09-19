# source this: shared caches so worktrees do not each grow their own
export WS_HOME="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
# Only meaningful for Nx projects: keeps one shared cache instead of one per worktree.
# Harmless otherwise; delete these two lines if you do not use Nx.
export NX_CACHE_DIRECTORY="$WS_HOME/.cache/nx"
export NX_DAEMON=false
