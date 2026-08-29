#!/bin/bash

usage() {
    cat <<EOF
Usage: $(basename "$0") [--dry-run] [--user USER] [container]

Arguments:
  container   Container name to enter. Default: slurmctld

Options:
  --dry-run   Print the docker exec command without running it
  --user USER Enter as a configured QFw test user instead of root
EOF
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
USER_FILE="${SCRIPT_DIR}/config/qfw-users.conf"
DRY_RUN=false
TARGET="slurmctld"
LOGIN_USER="root"

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --user)
            if [ "$#" -lt 2 ] || [ -z "${2:-}" ]; then
                echo "--user requires a value" >&2
                usage >&2
                exit 1
            fi
            LOGIN_USER="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            if [ "${TARGET}" != "slurmctld" ]; then
                echo "Too many arguments: $1" >&2
                usage >&2
                exit 1
            fi
            TARGET="$1"
            shift
            ;;
    esac
done

LOGIN_HOME="/root"
if [ "${LOGIN_USER}" != "root" ]; then
    if [ ! -r "${USER_FILE}" ]; then
        echo "Missing QFw user definition: ${USER_FILE}" >&2
        exit 1
    fi
    LOGIN_HOME="$(awk -F: -v user="${LOGIN_USER}" \
        '$1 == user { print $4 }' "${USER_FILE}")"
    if [ -z "${LOGIN_HOME}" ]; then
        echo "Unknown QFw test user: ${LOGIN_USER}" >&2
        exit 1
    fi
fi

if ${DRY_RUN}; then
    echo "Would run:"
    if [ "${LOGIN_USER}" = "root" ]; then
        echo "  docker exec -it ${TARGET} bash"
    else
        printf '  docker exec -it --user %s --env HOME=%s ' \
            "${LOGIN_USER}" "${LOGIN_HOME}"
        printf '%s %s bash --login\n' \
            "--workdir ${LOGIN_HOME}" "${TARGET}"
    fi
    exit 0
fi

set -xe

if [ "${LOGIN_USER}" = "root" ]; then
    docker exec -it "${TARGET}" bash
else
    docker exec -it --user "${LOGIN_USER}" \
        --env "HOME=${LOGIN_HOME}" --workdir "${LOGIN_HOME}" \
        "${TARGET}" bash --login
fi
