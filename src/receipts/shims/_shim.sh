#!/usr/bin/env bash
# receipts universal command shim
#
# Invoked under the name of the wrapped binary (e.g. /shims/pytest, /shims/npm).
# Logs invocation and exit to $RECEIPTS_EXEC_LOG (TSV), then execs the real
# binary found later in PATH.
#
# Log format (TSV, one record per line):
#   INVOKE\t<unix_seconds_float>\t<name>\t<cwd>\t<args_json>
#   EXIT\t<unix_seconds_float>\t<name>\t<exit_code>\t<status>
#
# Environment:
#   RECEIPTS_EXEC_LOG   path to the exec log (required)
#   RECEIPTS_SESSION    session id (optional, for context)

set -uo pipefail

NAME="$(basename "$0")"
LOG_FILE="${RECEIPTS_EXEC_LOG:-/dev/null}"
START="$(date -u +%s.%N)"

# JSON-encode argv. python3 is universally available wherever Claude Code,
# Aider, OpenCode, or any modern dev agent runs.
ARGS_JSON="$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1:]))' "$@" 2>/dev/null || echo '[]')"

printf 'INVOKE\t%s\t%s\t%s\t%s\n' "$START" "$NAME" "$PWD" "$ARGS_JSON" >> "$LOG_FILE"

# Find the real binary, skipping ourselves. readlink -f handles symlinks.
SELF="$(readlink -f "$0" 2>/dev/null || echo "$0")"
REAL=""
IFS=':' read -ra DIRS <<< "$PATH"
for d in "${DIRS[@]}"; do
    candidate="$d/$NAME"
    if [ -x "$candidate" ]; then
        resolved="$(readlink -f "$candidate" 2>/dev/null || echo "$candidate")"
        if [ "$resolved" != "$SELF" ]; then
            REAL="$candidate"
            break
        fi
    fi
done

if [ -z "$REAL" ]; then
    END="$(date -u +%s.%N)"
    printf 'EXIT\t%s\t%s\t%d\t%s\n' "$END" "$NAME" 127 "missing" >> "$LOG_FILE"
    echo "receipts shim: real '$NAME' not found in PATH" >&2
    exit 127
fi

"$REAL" "$@"
EXIT=$?
END="$(date -u +%s.%N)"
printf 'EXIT\t%s\t%s\t%d\t%s\n' "$END" "$NAME" "$EXIT" "ok" >> "$LOG_FILE"
exit $EXIT
