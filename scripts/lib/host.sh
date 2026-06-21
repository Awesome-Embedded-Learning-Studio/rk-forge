# scripts/lib/host.sh — host environment checks (WSL2 / Windows PATH contamination).
#
# WSL2 inherits Windows PATH entries (/mnt/c/Program Files/...) that break some
# builds — buildroot's support/dependencies/dependencies.mk rejects any PATH
# entry containing a space (or TAB/newline). Detect + warn; forge_clean_path
# strips /mnt/* + whitespace entries for the builds that need it (buildroot).
#
# Source after lib/log.sh. Convention: the orchestrator calls forge_warn_windows_path
# once at build start; buildroot uses `PATH=$(forge_clean_path) make ...`.

# 0 (true) if PATH contains /mnt/* entries or whitespace within an entry.
forge_is_windows_path_contaminated() {
  printf '%s' "${PATH:-}" | tr ':' '\n' | grep -qE '^/mnt/|[[:space:]]'
}

# warn (once is enough) if the host PATH is Windows-contaminated.
forge_warn_windows_path() {
  forge_is_windows_path_contaminated && \
    log_warn "host PATH has Windows entries (/mnt/... or whitespace) — breaks buildroot (dependencies.mk); forge_clean_path strips them" || true
}

# echo PATH with /mnt/* and whitespace-containing entries removed (the buildroot fix).
forge_clean_path() {
  printf '%s' "${PATH:-}" | tr ':' '\n' | grep -vE '^/mnt/|[[:space:]]' | paste -sd:
}
