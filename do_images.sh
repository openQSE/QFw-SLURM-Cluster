#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/qfw-install.env"

DEFAULT_IMAGE_NAME="qfw-slurm-cluster"
DEFAULT_IMAGE_TAG="rocky10.1"

usage() {
    cat <<EOF
Usage: $(basename "$0") [options]

List local Docker images relevant to this QFw Slurm cluster.

Options:
  --project              Show common QFw Slurm image names. This is default.
  --configured           Show only the image configured in qfw-install.env.
  --all                  Show all local Docker image repositories.
  --dangling             Show dangling local images.
  --repo NAME            Show images for repository NAME. May be repeated.
  --tag TAG              Restrict results to TAG.
  --history              Show docker history for one selected image.
  --include-intermediate Include intermediate images from docker image ls -a.
  --digests              Include image digests when Docker has them.
  -q, --quiet            Print image IDs only.
  --no-trunc             Do not truncate Docker image IDs.
  -h, --help             Show this help text.

Examples:
  ./do_images.sh
  ./do_images.sh --configured
  ./do_images.sh --all
  ./do_images.sh --repo ghcr.io/openqse/qfw-slurm-cluster
  ./do_images.sh --repo ghcr.io/openqse/qfw-slurm-cluster --tag 20260503-v1.0
  ./do_images.sh --configured --history
EOF
}

MODE="project"
INCLUDE_INTERMEDIATE=false
DIGESTS=false
QUIET=false
NO_TRUNC=false
HISTORY=false
TAG_FILTER=""
REPOS=()

while [ "$#" -gt 0 ]; do
    case "$1" in
        --project)
            MODE="project"
            shift
            ;;
        --configured)
            MODE="configured"
            shift
            ;;
        --all)
            MODE="all"
            shift
            ;;
        --dangling)
            MODE="dangling"
            shift
            ;;
        --repo)
            REPOS+=("${2:?missing value for --repo}")
            MODE="custom"
            shift 2
            ;;
        --tag)
            TAG_FILTER="${2:?missing value for --tag}"
            shift 2
            ;;
        --history)
            HISTORY=true
            shift
            ;;
        --include-intermediate)
            INCLUDE_INTERMEDIATE=true
            shift
            ;;
        --digests)
            DIGESTS=true
            shift
            ;;
        -q|--quiet)
            QUIET=true
            shift
            ;;
        --no-trunc)
            NO_TRUNC=true
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

IMAGE_NAME="${DEFAULT_IMAGE_NAME}"
IMAGE_TAG="${DEFAULT_IMAGE_TAG}"
if [ -f "${ENV_FILE}" ]; then
    set -a
    source "${ENV_FILE}"
    set +a
fi

if [ "${MODE}" = "configured" ]; then
    REPOS=("${IMAGE_NAME}")
    if [ -z "${TAG_FILTER}" ]; then
        TAG_FILTER="${IMAGE_TAG}"
    fi
elif [ "${MODE}" = "project" ]; then
    REPOS=(
        "${IMAGE_NAME}"
        "qfw-slurm-cluster"
        "qfw-slurm-env"
        "ghcr.io/openqse/qfw-slurm-cluster"
        "ghcr.io/openqse/qfw-slurm-env"
    )
elif [ "${MODE}" = "all" ] || [ "${MODE}" = "dangling" ]; then
    REPOS=()
fi

selected_image() {
    local repo

    if [ "${MODE}" = "configured" ]; then
        printf "%s:%s\n" "${IMAGE_NAME}" "${TAG_FILTER:-${IMAGE_TAG}}"
        return
    fi

    if [ "${#REPOS[@]}" -ne 1 ]; then
        cat <<EOF >&2
--history needs exactly one image target.

Use one of:
  ./do_images.sh --configured --history
  ./do_images.sh --repo NAME --tag TAG --history
EOF
        exit 1
    fi

    repo="${REPOS[0]}"
    if [ -z "${TAG_FILTER}" ]; then
        cat <<EOF >&2
--history with --repo needs --tag so the image reference is unambiguous.

Example:
  ./do_images.sh --repo ${repo} --tag ${IMAGE_TAG} --history
EOF
        exit 1
    fi

    printf "%s:%s\n" "${repo}" "${TAG_FILTER}"
}

if ${HISTORY}; then
    image_ref="$(selected_image)"
    history_args=(history)
    if ${NO_TRUNC}; then
        history_args+=(--no-trunc)
    fi

    echo "Image history for ${image_ref}"
    echo "GHCR allows up to 10 GB per layer and has a 10 minute upload timeout."
    docker "${history_args[@]}" "${image_ref}"
    exit 0
fi

docker_args=(image ls)
if ${INCLUDE_INTERMEDIATE}; then
    docker_args+=(-a)
fi
if ${DIGESTS}; then
    docker_args+=(--digests)
fi
if ${NO_TRUNC}; then
    docker_args+=(--no-trunc)
fi
if [ "${MODE}" = "dangling" ]; then
    docker_args+=(--filter dangling=true)
fi

if ${DIGESTS}; then
    docker_format='{{.Repository}}\t{{.Tag}}\t{{.Digest}}\t{{.ID}}'
    docker_format+='\t{{.CreatedSince}}\t{{.Size}}'
else
    docker_format='{{.Repository}}\t{{.Tag}}\t{{.ID}}'
    docker_format+='\t{{.CreatedSince}}\t{{.Size}}'
fi
docker_args+=(--format "${docker_format}")

repo_filter=""
if [ "${#REPOS[@]}" -gt 0 ]; then
    for repo in "${REPOS[@]}"; do
        if [ -z "${repo_filter}" ]; then
            repo_filter="${repo}"
        else
            repo_filter="${repo_filter}"$'\034'"${repo}"
        fi
    done
fi

quiet_flag=0
digests_flag=0
if ${QUIET}; then
    quiet_flag=1
fi
if ${DIGESTS}; then
    digests_flag=1
fi

docker_output="$(docker "${docker_args[@]}")"

printf "%s\n" "${docker_output}" | awk \
    -v repos="${repo_filter}" \
    -v tag_filter="${TAG_FILTER}" \
    -v quiet="${quiet_flag}" \
    -v digests="${digests_flag}" \
    'BEGIN {
        FS = "\t"
        repo_count = 0
        if (repos != "") {
            repo_count = split(repos, repo_list, "\034")
            for (idx = 1; idx <= repo_count; idx++) {
                repo_map[repo_list[idx]] = 1
            }
        }

        if (!quiet && digests) {
            printf "%-42s %-18s %-18s %-14s %-20s %s\n",
                "REPOSITORY", "TAG", "DIGEST", "IMAGE ID", "CREATED", "SIZE"
        } else if (!quiet) {
            printf "%-42s %-18s %-14s %-20s %s\n",
                "REPOSITORY", "TAG", "IMAGE ID", "CREATED", "SIZE"
        }
    }
    NF == 0 {
        next
    }
    {
        repo = $1
        tag = $2

        if (repo_count && !(repo in repo_map)) {
            next
        }
        if (tag_filter != "" && tag != tag_filter) {
            next
        }

        key = $0
        if (seen[key]++) {
            next
        }

        count++
        if (quiet) {
            if (digests) {
                print $4
            } else {
                print $3
            }
        } else if (digests) {
            printf "%-42s %-18s %-18s %-14s %-20s %s\n",
                $1, $2, $3, $4, $5, $6
        } else {
            printf "%-42s %-18s %-14s %-20s %s\n",
                $1, $2, $3, $4, $5
        }
    }
    END {
        if (count == 0 && !quiet) {
            print "No matching local Docker images." > "/dev/stderr"
        }
    }'
