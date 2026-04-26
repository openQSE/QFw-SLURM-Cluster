#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/qfw-install.env"
COMPOSE=(docker compose --env-file "${ENV_FILE}")
DELETE=false
DRY_RUN=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [delete] [--dry-run]

Arguments:
  delete      Stop services and remove containers and named volumes

Options:
  --dry-run   Print the compose stop/down commands without running them
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        delete)
            DELETE=true
            shift
            ;;
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
    printf ' %q\n' stop
    if ${DELETE}; then
        printf '  %q' "${COMPOSE[@]}"
        printf ' %q %q\n' down -v
    fi
    exit 0
fi

set -xe

"${COMPOSE[@]}" stop

if ${DELETE} ; then
    "${COMPOSE[@]}" down -v
fi
