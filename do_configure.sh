#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_BASE_DIR="${SCRIPT_DIR}/../qfw-container-base"
DEFAULT_IMAGE_NAME="qfw-slurm-cluster"
DEFAULT_IMAGE_TAG="rocky10.1"
DEFAULT_SLURM_TAG="slurm-25-05-0-1"
DEFAULT_QFW_BUILD_JOBS="4"
ENV_FILE="${SCRIPT_DIR}/qfw-install.env"
COMPOSE_ENV_FILE="${SCRIPT_DIR}/.env"

usage() {
    cat <<EOF
Usage: $(basename "$0") [options]

Options:
  --prefix PATH        Host workspace root to mount into the containers
                       Default: ${DEFAULT_BASE_DIR}
  --image NAME:TAG     Docker image repository and tag in one argument
  --image-name NAME    Docker image repository name
                       Default: ${DEFAULT_IMAGE_NAME}
  --image-tag TAG      Docker image tag
                       Default: ${DEFAULT_IMAGE_TAG}
  --slurm-tag TAG      Slurm source tag used at image build time
                       Default: ${DEFAULT_SLURM_TAG}
  --qfw-build-jobs N   Parallel build jobs for the image-contained QFw build
                       Default: ${DEFAULT_QFW_BUILD_JOBS}
  --dry-run            Print the resolved settings without creating anything
  -h, --help           Show this help text

This command prepares the mounted host workspace and writes the defaults used
by the helper scripts and docker compose into:
  ${ENV_FILE}
EOF
}

normalize_path() {
    local path="$1"
    local -a parts=()
    local -a normalized=()
    local part
    local output=""

    if [[ "${path}" != /* ]]; then
        path="${PWD}/${path}"
    fi

    while [[ "${path}" == *//* ]]; do
        path="${path//\/\///}"
    done

    IFS='/' read -r -a parts <<< "${path}"
    for part in "${parts[@]}"; do
        case "${part}" in
            ""|".")
                ;;
            "..")
                if [ "${#normalized[@]}" -gt 0 ]; then
                    unset 'normalized[${#normalized[@]}-1]'
                fi
                ;;
            *)
                normalized+=("${part}")
                ;;
        esac
    done

    if [ "${#normalized[@]}" -eq 0 ]; then
        printf '/\n'
        return
    fi

    for part in "${normalized[@]}"; do
        output="${output}/${part}"
    done
    printf '%s\n' "${output}"
}

BASE_DIR=""
IMAGE_NAME="${DEFAULT_IMAGE_NAME}"
IMAGE_TAG="${DEFAULT_IMAGE_TAG}"
SLURM_TAG="${DEFAULT_SLURM_TAG}"
QFW_BUILD_JOBS="${DEFAULT_QFW_BUILD_JOBS}"
DRY_RUN=false

while [ "$#" -gt 0 ]; do
    case "$1" in
        --prefix)
            BASE_DIR="${2:?missing value for --prefix}"
            shift 2
            ;;
        --image)
            IMAGE_SPEC="${2:?missing value for --image}"
            if [[ "${IMAGE_SPEC}" != *:* ]]; then
                echo "--image must look like NAME:TAG" >&2
                exit 1
            fi
            IMAGE_NAME="${IMAGE_SPEC%%:*}"
            IMAGE_TAG="${IMAGE_SPEC#*:}"
            shift 2
            ;;
        --image-name)
            IMAGE_NAME="${2:?missing value for --image-name}"
            shift 2
            ;;
        --image-tag)
            IMAGE_TAG="${2:?missing value for --image-tag}"
            shift 2
            ;;
        --slurm-tag)
            SLURM_TAG="${2:?missing value for --slurm-tag}"
            shift 2
            ;;
        --qfw-build-jobs)
            QFW_BUILD_JOBS="${2:?missing value for --qfw-build-jobs}"
            shift 2
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

if [ -z "${BASE_DIR}" ]; then
    BASE_DIR="${DEFAULT_BASE_DIR}"
fi

BASE_DIR="$(normalize_path "${BASE_DIR}")"
QFW_DIR="${BASE_DIR}/QFw"

validate_image_settings() {
    local image_name_pattern='^[a-z0-9]+([._-][a-z0-9]+)*(\/[a-z0-9]+([._-][a-z0-9]+)*)*$'

    if ! [[ "${IMAGE_NAME}" =~ ${image_name_pattern} ]]; then
        cat <<EOF >&2
Invalid IMAGE_NAME: ${IMAGE_NAME}

Docker image repository names must be lowercase and may contain path
components separated by '/', using only letters, digits, '.', '_' and '-'.

Examples:
  qfw-slurm-env
  openqse/qfw-slurm-env
EOF
        exit 1
    fi

    if [[ -z "${IMAGE_TAG}" ]]; then
        echo "IMAGE_TAG must not be empty." >&2
        exit 1
    fi
}

validate_qfw_build_jobs() {
    if ! [[ "${QFW_BUILD_JOBS}" =~ ^[1-9][0-9]*$ ]]; then
        echo "QFW_BUILD_JOBS must be a positive integer." >&2
        exit 1
    fi
}

print_settings() {
    echo "Resolved install settings:"
    echo "  ENV_FILE=${ENV_FILE}"
    echo "  COMPOSE_ENV_FILE=${COMPOSE_ENV_FILE}"
    echo "  IMAGE_NAME=${IMAGE_NAME}"
    echo "  IMAGE_TAG=${IMAGE_TAG}"
    echo "  SLURM_TAG=${SLURM_TAG}"
    echo "  QFW_BUILD_JOBS=${QFW_BUILD_JOBS}"
    echo "  QFW_CONTAINER_BASE=${BASE_DIR}"
    echo "  QFW_DIR=${QFW_DIR}"
    echo "  VENV_DIR=${BASE_DIR}/venv"
    echo "  BUILD_DIR=${BASE_DIR}/build"
    echo "  INSTALL_DIR=${BASE_DIR}/install"
    echo "  BENCHMARKS_DIR=${BASE_DIR}/benchmarks"
    echo "  ROCM_DIR=${BASE_DIR}/rocm"
}

validate_image_settings
validate_qfw_build_jobs

if ${DRY_RUN}; then
    print_settings
    cat <<EOF

Dry run only. No directories were created and ${ENV_FILE} was not written.
EOF
    exit 0
fi

mkdir -p \
    "${BASE_DIR}" \
    "${BASE_DIR}/venv" \
    "${BASE_DIR}/build" \
    "${BASE_DIR}/install" \
    "${BASE_DIR}/benchmarks" \
    "${BASE_DIR}/rocm"

cat > "${ENV_FILE}" <<EOF
SLURM_TAG=${SLURM_TAG}
QFW_BUILD_JOBS=${QFW_BUILD_JOBS}
IMAGE_NAME=${IMAGE_NAME}
IMAGE_TAG=${IMAGE_TAG}
QFW_CONTAINER_BASE=${BASE_DIR}
EOF

cp "${ENV_FILE}" "${COMPOSE_ENV_FILE}"

echo "Prepared host workspace at: ${BASE_DIR}"
echo "Wrote helper defaults to: ${ENV_FILE}"
echo "Wrote compose defaults to: ${COMPOSE_ENV_FILE}"
echo "  IMAGE_NAME=${IMAGE_NAME}"
echo "  IMAGE_TAG=${IMAGE_TAG}"
echo "  SLURM_TAG=${SLURM_TAG}"
echo "  QFW_BUILD_JOBS=${QFW_BUILD_JOBS}"
echo "  QFW_CONTAINER_BASE=${BASE_DIR}"

if [ -d "${QFW_DIR}/.git" ] || [ -f "${QFW_DIR}/README.md" ]; then
    echo "Found QFw checkout at: ${QFW_DIR}"
else
    cat <<EOF
Missing QFw checkout at: ${QFW_DIR}

Clone or place the QFw source tree there before starting the cluster, for example:
  git clone <QFw-repo-url> "${QFW_DIR}"

The persistent Python venv is intentionally not created here. Create it later from
inside the built container so it matches the container Python runtime:
  python3 -m venv /workspace/qfw-container-base/venv
EOF
fi
