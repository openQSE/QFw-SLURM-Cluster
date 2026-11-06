#!/bin/bash
#
# Run hello.py on the site NWQ-Sim QPM. One node runs the COMPSs master and the
# other two run the tasks, four at a time each.
#
#SBATCH --job-name=compss-hello
#SBATCH --account=qfw-test
#SBATCH --partition=normal
#SBATCH --nodes=3
#SBATCH --ntasks-per-node=1
#SBATCH --time=00:05:00
#SBATCH --output=compss-hello-%j.out
# Reserve the QPM for what the whole job sends: 8 one-qubit circuits.
#SBATCH --qpu=nwqsim
#SBATCH --workload-kind=hybrid
#SBATCH --circ-count=16
#SBATCH --max-qubits=1
#SBATCH --max-depth=16
#SBATCH --max-shots=1024

# The site configuration refers to this; a login shell has it already.
export QFW_SHARED_ROOT=${QFW_SHARED_ROOT:-/workspace/qfw-container-base}

# qfw-activate is not written for set -u, so activate before enabling it.
source "${QFW_INSTALL_PREFIX:-/opt/openqse/qfw}/bin/qfw-activate" \
	--venv "${QFW_VENV:-/opt/openqse/qfw-venv}"
set -euo pipefail

# Start QFw for this job, and stop it when the job ends.
qfw-setup --site-config "${QFW_SITE_CONFIG:-/etc/openqse/qfw/site.yaml}"
trap 'qfw-teardown || true' EXIT

# run-local.sh --trace sets COMPSS_TRACING.
qfw-compss-launch ${COMPSS_TRACING:+--tracing} \
	--launch-option=--graph=true \
	--launch-option=--summary \
	"${QFW_SHARED_ROOT}/compss-examples/hello/hello.py"
