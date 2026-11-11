#!/usr/bin/env bash
set -euo pipefail
sampler=$1
circuit=$2
provider=$3
shots=$4
output=$5
application=$6
source "${QFW_INSTALL_PREFIX:-/opt/openqse/qfw}/bin/qfw-activate" --venv "${application}"
run_dir=${output}/qfw
cleanup() {
    qfw-teardown --run-dir "${run_dir}" --keep-run-dir || true
    qfw-deactivate || true
}
trap cleanup EXIT
qfw-setup --site-config "${QFW_SITE_CONFIG:-/etc/openqse/qfw/site.yaml}" --run-dir "${run_dir}"
qfw-srun --run-dir "${run_dir}" --nodes=1 --ntasks=1 -- "${sampler}" \
    --circuit "${circuit}" --provider "${provider}" --shots "${shots}" --out "${output}/counts.json"
test -s "${output}/counts.json"
