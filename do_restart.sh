#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/qfw-install.env"
COMPOSE=(docker compose --env-file "${ENV_FILE}")
DRY_RUN=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [--dry-run]

Options:
  --dry-run   Print the compose restart command without running it
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [ ! -f "${ENV_FILE}" ]; then
    echo "Missing ${ENV_FILE}. Run ./do_configure.sh first." >&2
    exit 1
fi

if ${DRY_RUN}; then
    echo "Would run:"
    printf '  %q' "${COMPOSE[@]}"
    printf ' %q\n' restart
    exit 0
fi

set -xe

"${COMPOSE[@]}" restart
