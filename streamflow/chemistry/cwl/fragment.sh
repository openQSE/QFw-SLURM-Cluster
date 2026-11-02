#!/usr/bin/env bash
set -euo pipefail
fragment=$1
backend=$2
output=$3
entrypoint=${PWD}/fragment.py
run_dir=${output}/qfw
source "${QFW_INSTALL_PREFIX:-/opt/openqse/qfw}/bin/qfw-activate" \
    --venv "${QFW_VENV:-/opt/openqse/qfw-venv}"
cleanup() {
    qfw-teardown --run-dir "${run_dir}" --keep-run-dir || true
    qfw-deactivate || true
}
trap cleanup EXIT
qfw-setup --site-config "${QFW_SITE_CONFIG:-/etc/openqse/qfw/site.yaml}" --run-dir "${run_dir}"
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-1}
export OPENBLAS_NUM_THREADS=${OMP_NUM_THREADS} MKL_NUM_THREADS=${OMP_NUM_THREADS} PYTHONUNBUFFERED=1
qfw-srun --run-dir "${run_dir}" --nodes=1 --ntasks=1 -- "${entrypoint}" \
    "${fragment}" "${backend}" "${output}/workflow-result.json" "${QFW_SHOTS}" \
    "${MAX_MACRO_ITERATIONS}" "${MAX_AMPLITUDE_ITERATIONS}" "${MAX_ORBITAL_ITERATIONS}"
test -s "${output}/workflow-result.json"
