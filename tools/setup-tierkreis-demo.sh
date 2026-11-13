#!/bin/bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cluster_root=$(cd "${script_dir}/.." && pwd)
project=/workspace/qfw-container-base/tierkreis-sc-demo
venv="${project}/.runtime/venv"
commit=c5afec0a3f063229954bfa5ca4eb03a38859cb70

docker info >/dev/null
if [[ $(docker inspect slurmctld --format '{{.State.Running}}' 2>/dev/null || true) != true ]]; then
    (cd "${cluster_root}" && ./do_startup.sh)
fi

if ! docker exec slurmctld bash -c \
    'test -r /usr/include/nlohmann/json.hpp && command -v pkg-config >/dev/null && pkg-config --exists nlohmann_json'; then
    echo 'Tierkreis setup requires nlohmann-json headers and pkg-config in the cluster image. Rebuild the image, then recreate the cluster containers before running this setup.' >&2
    exit 1
fi

docker exec -i slurmctld bash -s -- "${project}" "${commit}" <<'EOF'
set -euo pipefail
export GIT_TERMINAL_PROMPT=0
project="$1"
commit="$2"
if [[ ! -d "${project}/.git" ]]; then
    git clone --branch main --single-branch \
        https://github.com/Quantinuum/tierkreis-sc-demo.git "${project}"
fi
git -c safe.directory="${project}" -C "${project}" fetch origin main
git -c safe.directory="${project}" -C "${project}" checkout --detach "${commit}"
install -d -o user-a -g user-a -m 0755 \
    "${project}/.runtime" "${project}/.runtime/assets" "${project}/.runtime/qfw"
EOF

# The application environment and demo checkout are shared by all nodes.
docker exec -i --user user-a --env HOME=/workspace/home/user-a \
    --workdir "${project}" \
    -e UV_PROJECT_ENVIRONMENT="${venv}" \
    -e UV_CACHE_DIR=/tmp/tierkreis-demo-uv-cache-user-a \
     slurmctld bash -s <<'EOF'
set -euo pipefail
uv sync --python /opt/openqse/qfw-venv/bin/python --locked --no-dev --group qfw
uv pip check --python "${UV_PROJECT_ENVIRONMENT}"
EOF

for node in slurmctld c1 c2 c3 c4 c5 c6 c7 c8; do
    docker exec -i --user user-a --env HOME=/workspace/home/user-a \
        --env OPENSSL_armcap=0 \
        --workdir "${project}" "${node}" bash -s -- "${venv}" <<'EOF'
set -euo pipefail
venv="$1"
test -x "${venv}/bin/python"
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
echo "Tierkreis demo ready in ${project} (venv ${venv}, profile qfw-slurm)."
