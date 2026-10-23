#!/bin/bash
# Run QFw's Pulser example on a Pasqal Cloud device from the
# Docker host, in one command:
#   1. read your own Pasqal Cloud login (pasqal_login.py),
#   2. allocate a two-group heterogeneous job in slurmctld,
#   3. activate the QFw build and run examples/qfw_pulser.sh,
#   4. print the results table; the full log stays in pulser-<time>.log.
#
# Usage: run_pulser_example.sh [--container NAME] [--image-install]
#                              [qfw_pulser.sh options...]
#   --container NAME  container to run in (default: slurmctld)
#   --image-install   use the image's QFw (QFW_PREFIX, QFW_VENV) instead of
#                     the developer build do_qfw_build.sh makes
# Everything else goes to qfw_pulser.sh, e.g.
#   run_pulser_example.sh                                  # EMU_FREE
#   run_pulser_example.sh --device-id pasqal-fresnel --atoms 42
#
# The login is read from your environment or ~/.pasqal/config on this host,
# written to an owner-only file in a private temporary directory, passed to
# the container with --env-file, and the file is removed afterwards. It is
# never printed and never written into the shared mount.
#
# The allocation is limited to two hours, enough for FRESNEL's queue. Ctrl-C
# cancels it: docker exec does not pass the signal on, so the script runs
# scancel on the job itself.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
container=slurmctld
install=developer
while [[ $# -gt 0 ]]; do
	case "$1" in
		--container) container="$2"; shift 2 ;;
		--image-install) install=image; shift ;;
		-h|--help) awk 'NR > 1 && !/^#/ { exit } NR > 1 { sub(/^# ?/, ""); print }' "$0"; exit 0 ;;
		*) break ;;
	esac
done

envfile="$(python3 "${here}/pasqal_login.py")"
log="pulser-$(date +%Y%m%d-%H%M%S).log"
finish() {
	rm -rf "$(dirname "${envfile}")"
	echo "full log: ${log}"
}
interrupted() {
	local job
	job="$(sed -n 's/.*Granted job allocation \([0-9]*\).*/\1/p' "${log}" \
		2>/dev/null | head -n1)"
	if [[ -n "${job}" ]] && docker exec "${container}" scancel "${job}"; then
		echo "cancelled Slurm job ${job}"
	fi
	exit 130
}
trap finish EXIT
trap interrupted INT TERM HUP

echo "QFw Pulser example in ${container} (${install} QFw install): $*"
docker exec -i --env-file "${envfile}" -e QFW_RUN_INSTALL="${install}" \
	-w /workspace/qfw-container-base "${container}" \
	bash -s -- "$@" <<'REMOTE' 2>&1 | tee "${log}" | awk '
	/Granted job allocation/ { sub(/^salloc: /, ""); print "[slurm] " $0; next }
	/"service_id": "shim-/ && !seen++ {
		gsub(/[",]/, ""); print "[qfw]   reserved QPM " $2; next }
	/needs at least/ { print "[pulser] " $0; next }
	/^Pulser program on/ { table = 1 }
	table && /^QFW_EXAMPLE_RESULT/ { table = 0 }
	table && NF { print; next }
	tolower($0) ~ /traceback|error|unbound variable/ { print "[error] " $0 }
'
set -euo pipefail
# One application group and one service group, as the local QFw profile
# expects (docs/usage.md in QFw, "Heterogeneous Slurm Allocation").
salloc -p normal -N1 -n1 --time=02:00:00 : -p normal -N1 -n1 --time=02:00:00 \
	bash -s -- "$@" <<'ALLOCATION'
set -euo pipefail
base=/workspace/qfw-container-base
if [[ "${QFW_RUN_INSTALL}" == developer ]]; then
	prefix="${base}/qfw-install" venv="${base}/qfw-venv"
else
	prefix="${QFW_PREFIX}" venv="${QFW_VENV}"
fi
export QFW_SHARED_ROOT="${base}"
export QFW_RUN_BASE_DIR="${base}/qfw-runs/job-${SLURM_JOB_ID}"
mkdir -p "${QFW_RUN_BASE_DIR}"
# shellcheck disable=SC1091
source "${prefix}/bin/qfw-activate" --venv "${venv}"
cd "${QFW_SHARE_DIR}/examples"
./qfw_pulser.sh "$@"
ALLOCATION
REMOTE
