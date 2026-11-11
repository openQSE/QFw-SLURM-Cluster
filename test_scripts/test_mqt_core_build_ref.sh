#!/usr/bin/env bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temporary="$(mktemp -d)"
trap 'rm -rf "${temporary}"' EXIT
cp "${repo_dir}/do_configure.sh" "${repo_dir}/do_build.sh" "${temporary}/"
release_ref=d76be496512c8707f165e18f152bd5f11b8a5665
custom_ref=1111111111111111111111111111111111111111
export DOCKER_LOG="${temporary}/docker.log"
unset MQT_CORE_REF

docker() { printf '%s\n' "$@" >"${DOCKER_LOG}"; }
export -f docker

check_build_ref() {
    local expected="$1"
    bash "${temporary}/do_build.sh" --dry-run >"${temporary}/dry-run.log"
    grep -Fq -- "--build-arg MQT_CORE_REF=${expected} " "${temporary}/dry-run.log"
    bash "${temporary}/do_build.sh" >"${temporary}/build.log"
    grep -Fxq "MQT_CORE_REF=${expected}" "${DOCKER_LOG}"
    grep -Fxq "MQT_CORE_SOURCE_REVISION=${expected}" "${DOCKER_LOG}"
}

bash "${temporary}/do_configure.sh" --prefix "${temporary}/workspace" \
    --qfw-ref "${custom_ref}" --qfw-slurm-ref "${custom_ref}" \
    >"${temporary}/configure.log"
grep -Fxq "MQT_CORE_REF=${release_ref}" "${temporary}/qfw-install.env"
grep -Fxq "ARG MQT_CORE_REF=${release_ref}" "${repo_dir}/Dockerfile"
check_build_ref "${release_ref}"

sed '/^MQT_CORE_REF=/d' "${temporary}/qfw-install.env" >"${temporary}/without-ref.env"
mv "${temporary}/without-ref.env" "${temporary}/qfw-install.env"
check_build_ref "${release_ref}"

bash "${temporary}/do_configure.sh" --prefix "${temporary}/workspace" \
    --qfw-ref "${custom_ref}" --qfw-slurm-ref "${custom_ref}" \
    --mqt-core-ref "${custom_ref}" >"${temporary}/configure.log"
check_build_ref "${custom_ref}"

echo "MQT Core build refs passed: release defaults, missing setting, explicit override"
