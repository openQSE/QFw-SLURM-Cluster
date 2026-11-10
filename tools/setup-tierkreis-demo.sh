#!/bin/bash
set -euo pipefail

project=/workspace/qfw-container-base/tierkreis-sc-demo
venv=/opt/openqse/qfw-venv
branch=sqd-example

docker exec -i slurmctld bash -s -- "${project}" "${branch}" <<'EOF'
set -euo pipefail
export GIT_TERMINAL_PROMPT=0
project="$1"
branch="$2"
if [[ ! -d "${project}/.git" ]]; then
    git clone --branch "${branch}" --single-branch \
        https://github.com/Quantinuum/tierkreis-sc-demo.git "${project}"
fi
git -c safe.directory="${project}" -C "${project}" pull --ff-only origin "${branch}"
install -d -o user-a -g user-a -m 0755 \
    "${project}/.runtime" "${project}/.runtime/assets" "${project}/.runtime/qfw"
EOF

# QFw Python environments are node-local; the source and build cache are shared.
for node in slurmctld c1 c2 c3 c4 c5 c6 c7 c8; do
    docker exec -i --workdir "${project}" \
        -e UV_PROJECT_ENVIRONMENT="${venv}" \
        -e UV_CACHE_DIR="${project}/.runtime/build/uv-cache" \
        -e CARGO_HOME="${project}/.runtime/build/cargo-home" \
        -e CARGO_TARGET_DIR="${project}/.runtime/build/cargo-target" \
        -e RUSTUP_HOME="${project}/.runtime/build/rustup" \
        -e RUSTUP_TOOLCHAIN=stable -e CARGO_BUILD_JOBS=2 \
        -e OPENSSL_armcap=0 "${node}" bash -s -- "${venv}" <<'EOF'
set -euo pipefail
venv="$1"
test -x "${venv}/bin/python"
rustup toolchain install stable --profile minimal --no-self-update --no-update
uv sync --python "${venv}/bin/python" --locked --no-dev --inexact \
    --reinstall-package tkr-fmo-control-worker --reinstall-package tkr-fmo-chemistry-worker \
    --reinstall-package tkr-fmo-quantum-worker --reinstall-package tkr-sqd-control-worker \
    --reinstall-package tkr-sqd-quantum-worker --reinstall-package tkr-sqd-sbd-worker
source /opt/openqse/qfw/bin/qfw-activate --venv "${venv}"
cd /tmp
"${venv}/bin/python" -c 'import tierkreis._tierkreis, qfw_qiskit, tkr_fmo_chemistry_worker_impl, tkr_sqd_control_worker_impl, tkr_sqd_quantum_worker_impl'
EOF
done

docker exec --workdir "${project}" slurmctld \
    bash tkr/workers/sqd_sbd_worker/native/build_sbd.sh
for node in slurmctld c1 c2 c3 c4 c5 c6 c7 c8; do
    docker exec --user user-a --workdir "${project}" "${node}" bash -c '
        set -euo pipefail
        test -w .runtime
        test -x tkr/workers/sqd_sbd_worker/native/diag
        libraries="$(ldd tkr/workers/sqd_sbd_worker/native/diag)"
        if grep -q "not found" <<<"${libraries}"; then
            echo "${libraries}" >&2
            exit 1
        fi
    '
done
for target in directory nwqsim gateway; do
    docker exec slurmctld qfw-site-services start --target "${target}"
done
echo "Tierkreis demo ready in ${project} (QFw environment, profile qfw-slurm)."
