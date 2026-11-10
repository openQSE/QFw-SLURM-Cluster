#!/usr/bin/env bash
set -euo pipefail
source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cluster_root=$(cd "${source_dir}/../.." && pwd)
source "${cluster_root}/qfw-install.env"
app_user=${QFW_USER:-user-a}
[[ ${app_user} != root ]] || { echo 'Use a non-root application user' >&2; exit 2; }
workspace=/workspace/qfw-container-base/streamflow-sqd
docker exec slurmctld bash -c 'mkdir -p "$1" && chown "$2:$2" "$1" && chmod 755 "$1"' _ "${workspace}" "${app_user}"
COPYFILE_DISABLE=1 tar --no-xattrs -C "${source_dir}" --exclude=__pycache__ -cf - . | \
    docker exec -i --user "${app_user}" slurmctld tar --no-same-owner -xf - -C "${workspace}"
docker exec --user "${app_user}" slurmctld rm -rf "${workspace}/slurm"
docker exec -i --user "${app_user}" slurmctld bash -c 'cat > "$1/qfw_sampler.py"' _ "${workspace}" \
    < "${cluster_root}/prefect/qfw_sampler.py"
docker exec -i --user "${app_user}" --env "SQD_ROOT=${workspace}" slurmctld bash -s <<'INSTALL'
set -euo pipefail
export UV_CACHE_DIR=/tmp/uv-cache-$(id -un)
export UV_LINK_MODE=copy
[[ -x ${SQD_ROOT}/coordinator/bin/python ]] || uv venv --quiet "${SQD_ROOT}/coordinator"
uv pip install --quiet --python "${SQD_ROOT}/coordinator" -r "${SQD_ROOT}/requirements.txt"
[[ -x ${SQD_ROOT}/application/bin/python ]] || uv venv --quiet --python /opt/openqse/qfw-venv/bin/python "${SQD_ROOT}/application"
uv pip freeze --quiet --python /opt/openqse/qfw-venv | sed '/ @ file:/d' > "${SQD_ROOT}/base.txt"
uv pip install --quiet --python "${SQD_ROOT}/application" -r "${SQD_ROOT}/base.txt"
uv pip install --quiet --python "${SQD_ROOT}/application" -c "${SQD_ROOT}/base.txt" -r "${SQD_ROOT}/application.txt"
ffsim_ok() {
    ("${SQD_ROOT}/application/bin/python" -c 'import ffsim; ffsim.apply_orbital_rotation(ffsim.hartree_fock_state(2,(1,1)),ffsim.random.random_orthogonal(2,seed=0),2,(1,1))') >/dev/null 2>&1
}
if ! ffsim_ok; then
    CARGO_HOME="${SQD_ROOT}/cargo" uv pip install --quiet --python "${SQD_ROOT}/application" \
        --reinstall --no-deps --no-binary ffsim ffsim==0.0.84
    ffsim_ok
fi
if [[ ! -d ${SQD_ROOT}/source/.git ]]; then
    git clone --quiet https://github.com/qiskit-community/qcsc-prefect.git "${SQD_ROOT}/source"
fi
git -C "${SQD_ROOT}/source" checkout --quiet --detach 96fed8eed8aa00966342951ec1e9957d5f40fd80
native=${SQD_ROOT}/source/algorithms/sbd/native
if [[ ! -x ${native}/diag ]]; then
    (cd "${native}" && bash build_sbd_slurm.sh)
fi
INSTALL
for target in directory nwqsim gateway; do
    docker exec slurmctld qfw-site-services start --target "${target}"
done
printf 'Ready: ./streamflow/sqd/run-local.sh\n'
