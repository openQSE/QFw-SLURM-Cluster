#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/qfw-install.env"

usage() {
    cat <<EOF
Usage: $(basename "$0") [--dry-run] [--force]

Build the configured container image. If ${ENV_FILE} does not exist yet,
run ./do_configure.sh first with its default settings.

Options:
  --dry-run   Print the install/bootstrap and docker build steps without running them
  --force     Stop and remove the current compose stack, then rebuild with --no-cache
EOF
}

DRY_RUN=false
FORCE=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --force)
            FORCE=true
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
    if ${DRY_RUN}; then
        echo "Would run:"
        echo "  ./do_configure.sh"
    else
        echo "Missing ${ENV_FILE}. Running ./do_configure.sh with defaults."
        "${SCRIPT_DIR}/do_configure.sh"
    fi
fi

if ${FORCE}; then
    if ${DRY_RUN}; then
        echo "Would run:"
        echo "  ./do_stop.sh delete"
    else
        "${SCRIPT_DIR}/do_stop.sh" delete
    fi
fi

if ${DRY_RUN}; then
    if [ -f "${ENV_FILE}" ]; then
        set -a
        source "${ENV_FILE}"
        set +a
        echo "Would run:"
        if ${FORCE}; then
            echo "  docker build --no-cache -t ${IMAGE_NAME}:${IMAGE_TAG} --build-arg SLURM_TAG=${SLURM_TAG} ${SCRIPT_DIR}"
        else
            echo "  docker build -t ${IMAGE_NAME}:${IMAGE_TAG} --build-arg SLURM_TAG=${SLURM_TAG} ${SCRIPT_DIR}"
        fi
    else
        cat <<EOF
Dry run only. ${ENV_FILE} does not exist yet, so the final image values would
come from ./do_configure.sh defaults unless you create the file first.
EOF
    fi
    exit 0
fi

set -a
source "${ENV_FILE}"
set +a

echo "Building ${IMAGE_NAME}:${IMAGE_TAG} with SLURM_TAG=${SLURM_TAG}"

if ${FORCE}; then
    docker build \
        --no-cache \
        -t "${IMAGE_NAME}:${IMAGE_TAG}" \
        --build-arg "SLURM_TAG=${SLURM_TAG}" \
        "${SCRIPT_DIR}"
else
    docker build \
        -t "${IMAGE_NAME}:${IMAGE_TAG}" \
        --build-arg "SLURM_TAG=${SLURM_TAG}" \
        "${SCRIPT_DIR}"
fi
