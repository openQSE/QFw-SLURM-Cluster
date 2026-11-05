#!/bin/bash
#
# COMPSs + QFw: chemistry_he's He4 FMO-VQE on the site NWQ-Sim QPM.
#
# setup-local.sh copies this directory to the shared directory; run-local.sh submits it as a test user.
#
# One node runs the COMPSs master, the other two run the ten fragment tasks,
# four at a time each. The quantum options reserve one allocation-wide slice
# of the NWQ-Sim QPM. It has to cover every circuit all ten VQE runs submit:
# with the default limits each fragment makes about 100 estimator calls of 3
# circuits, up to 10 qubits for the dimers and 4096 shots per circuit.
#
#SBATCH --job-name=compss-chemistry
#SBATCH --account=qfw-test
#SBATCH --partition=normal
#SBATCH --nodes=3
#SBATCH --ntasks-per-node=1
#SBATCH --time=01:00:00
#SBATCH --output=compss-chemistry-%j.out
#SBATCH --qpu=nwqsim
#SBATCH --workload-kind=hybrid
#SBATCH --circ-count=8000
#SBATCH --max-qubits=10
#SBATCH --max-depth=1000
#SBATCH --max-shots=4096

# The site configuration refers to this; a login shell has it already.
export QFW_SHARED_ROOT=${QFW_SHARED_ROOT:-/workspace/qfw-container-base}

# qfw-activate is not written for set -u, so activate before enabling it.
source "${QFW_INSTALL_PREFIX:-/opt/openqse/qfw}/bin/qfw-activate" \
	--venv "${QFW_VENV:-/opt/openqse/qfw-venv}"
set -euo pipefail

echo "nodes: ${SLURM_JOB_NODELIST}  reservations: ${QFW_RESERVATIONS:-none}"

qfw-setup --site-config "${QFW_SITE_CONFIG:-/etc/openqse/qfw/site.yaml}"
trap 'qfw-teardown || true' EXIT

# Four fragment tasks share each node's four CPUs.
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1

example_dir=${CHEMISTRY_EXAMPLE_DIR:-${QFW_SHARED_ROOT}/compss-chemistry}
chemistry=${CHEMISTRY_ROOT:-${example_dir}/chemistry_he}

qfw-compss-launch --pythonpath "${chemistry}" \
	--launch-option=--graph=true \
	--launch-option=--summary \
	"${example_dir}/he4_fmo_vqe.py" \
	--fcidump "${chemistry}/He4/He1-4.FCIDUMP" \
	--provider nwqsim \
	--shots 4096 \
	--max-macro-iterations "${MAX_MACRO_ITERATIONS:-2}" \
	--max-amplitude-iterations "${MAX_AMPLITUDE_ITERATIONS:-50}" \
	--max-orbital-iterations "${MAX_ORBITAL_ITERATIONS:-1}" \
	--output "${SLURM_SUBMIT_DIR}/compss-chemistry-${SLURM_JOB_ID}.json"
