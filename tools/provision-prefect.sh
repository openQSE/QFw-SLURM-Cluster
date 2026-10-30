#!/bin/bash

# Provision the qcsc-prefect SQD closed-loop environment on the running
# cluster: a dedicated Python venv beside the image's QFw venv, the
# qcsc-prefect checkout, the native SBD solver and the quantum-stage sampler,
# all inside one workspace on the shared mount that root creates and the
# application user owns, so they survive a container recreate and never
# depend on who owns the mount root (a Linux host keeps the host user's uid
# there). Rerunnable. See docs/recipes/run-prefect-sqd-closed-loop.md.

set -euo pipefail

user="${QFW_PREFECT_USER:-user-a}"
container="${QFW_PREFECT_CONTAINER:-slurmctld}"
workspace="${QFW_PREFECT_ROOT:-/workspace/qfw-container-base/qfw-prefect}"
venv="${QFW_PREFECT_VENV:-${workspace}/venv}"
checkout="${QCSC_PREFECT_DIR:-${workspace}/qcsc-prefect}"
repo="${QCSC_PREFECT_REPO:-https://github.com/qiskit-community/qcsc-prefect.git}"
# qcsc-prefect commit validated with this recipe, including QFw support and the
# H2/STO-3G FCIDUMP used by the fake-device pipe-cleaner. Override to follow a
# newer commit or branch.
ref="${QCSC_PREFECT_REF:-6a441958bf4fdbb78c0e173f230950020c55184d}"
image_venv="${QFW_IMAGE_VENV:-/opt/openqse/qfw-venv}"
prefix="${QFW_PREFECT_PREFIX:-/opt/openqse/qfw}"

die() {
	echo "qfw-prefect: $*" >&2
	exit 1
}

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

docker inspect --format '{{.State.Running}}' "${container}" 2>/dev/null |
	grep -qx true || die "container ${container} is not running"
docker exec "${container}" id -u "${user}" >/dev/null 2>&1 ||
	die "user ${user} does not exist in ${container}; run tools/provision-qfw-cluster.sh first"

echo "qfw-prefect: provisioning as ${user} in ${container}"
echo "qfw-prefect:   workspace ${workspace}"
echo "qfw-prefect:   venv      ${venv}"
echo "qfw-prefect:   checkout  ${checkout} at ${ref}"

# The workspace itself is the one thing done as root: the shared mount's
# root belongs to whoever owns it on the host, so the application user can
# create nothing there directly. Only the workspace directory and its bin
# change hands; nothing below them is touched.
docker exec "${container}" bash -c '
	set -e
	mkdir -p "$1" "$1/bin"
	chown "$2:$2" "$1" "$1/bin"
	chmod 0755 "$1" "$1/bin"
' _ "${workspace}" "${user}"
docker exec -u "${user}" "${container}" test -w "${workspace}" ||
	die "${workspace} is not writable by ${user} in ${container}"

# The quantum-stage sampler and its submitter, read by jobs on every node
# (docs/recipes/run-quantum-stage-through-qfw-slurm.md). Written as the
# user, since the workspace is theirs.
for name in qfw_sampler.py qfw_slurm_sampler.py; do
	docker exec -i -u "${user}" "${container}" \
		bash -c 'cat >"$1" && chmod 0644 "$1"' _ "${workspace}/bin/${name}" \
		<"${script_dir}/prefect/${name}"
done
echo "qfw-prefect:   sampler   ${workspace}/bin"

docker exec -i -u "${user}" \
	-e "PREFECT_VENV=${venv}" \
	-e "QCSC_DIR=${checkout}" \
	-e "QCSC_REPO=${repo}" \
	-e "QCSC_REF=${ref}" \
	-e "IMAGE_VENV=${image_venv}" \
	-e "PREFIX_DIR=${prefix}" \
	"${container}" bash -s <<'INNER'
set -euo pipefail

# The user's cache would land on the shared virtiofs mount; keep it local.
export UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/uv-cache-$(id -un)}"

say() {
	printf 'qfw-prefect: %s\n' "$*"
}

# 1. The qcsc-prefect checkout, detached at the requested commit or branch.
if [[ ! -d "${QCSC_DIR}/.git" ]]; then
	say "cloning ${QCSC_REPO}"
	git clone --quiet "${QCSC_REPO}" "${QCSC_DIR}"
fi
git -C "${QCSC_DIR}" fetch --quiet origin
if git -C "${QCSC_DIR}" rev-parse --verify --quiet \
		"${QCSC_REF}^{commit}" >/dev/null; then
	git -C "${QCSC_DIR}" checkout --quiet --detach "${QCSC_REF}"
else
	git -C "${QCSC_DIR}" checkout --quiet --detach "origin/${QCSC_REF}"
fi
say "qcsc-prefect at $(git -C "${QCSC_DIR}" rev-parse --short HEAD)"

# 2. The image venv's exact package set, used as the base of the new venv
#    and as constraints, so Prefect's dependencies cannot move the QFw pins
#    (qiskit, qrmi, the QDMI adapters). The one path-installed package,
#    qfw-slurm's gateway, is not needed by the workflow.
base="${PREFECT_VENV}.base.txt"
override="${PREFECT_VENV}.override.txt"
mkdir -p "$(dirname "${PREFECT_VENV}")"
uv pip freeze --python "${IMAGE_VENV}" 2>/dev/null |
	grep -v ' @ file://' | grep -v '^ruamel-yaml==' >"${base}"
# The IQM QDMI adapter's iqm-exa-common pins ruamel-yaml 0.17, while every
# pydantic_numpy release that supports NumPy 2.5 (the SBD workflow's models)
# needs 0.18. Nothing on the Prefect path uses iqm-exa-common, so this venv
# overrides that one pin instead of carrying a pydantic_numpy that cannot
# import under NumPy 2.5.
printf 'ruamel-yaml>=0.18.5,<0.19\n' >"${override}"
say "$(wc -l <"${base}" | tr -d ' ') packages pinned from ${IMAGE_VENV}"

# 3. The venv itself.
python="$(readlink -f "${IMAGE_VENV}/bin/python")"
if [[ ! -x "${PREFECT_VENV}/bin/python" ]]; then
	say "creating ${PREFECT_VENV} with ${python}"
	uv venv --quiet --python "${python}" "${PREFECT_VENV}"
fi
say "installing the image venv's package set"
uv pip install --quiet --python "${PREFECT_VENV}" --override "${override}" \
	-r "${base}"

# 4. qcsc-prefect, the same way its tutorial installs it: the four framework
#    packages without dependencies, then the workflow utility and the SBD
#    workflow with its optional Ray task runner, which pulls Prefect, Ray,
#    ffsim, pyscf and qiskit-addon-sqd.
say "installing the qcsc-prefect packages"
uv pip install --quiet --python "${PREFECT_VENV}" --no-deps \
	--override "${override}" \
	-e "${QCSC_DIR}/packages/qcsc-prefect-core" \
	-e "${QCSC_DIR}/packages/qcsc-prefect-adapters" \
	-e "${QCSC_DIR}/packages/qcsc-prefect-blocks" \
	-e "${QCSC_DIR}/packages/qcsc-prefect-executor"
say "installing the SBD workflow and its dependencies"
# pydantic_numpy 9 is the first release that imports under NumPy 2.5; the
# workflow leaves it unpinned, and an older release already present would
# otherwise satisfy it. Prefect 3.8.8's server still passes min_items to
# FastAPI's Body(), which FastAPI dropped after 0.149, inside the range
# Prefect allows; hold FastAPI where the server starts.
uv pip install --quiet --python "${PREFECT_VENV}" -c "${base}" \
	--override "${override}" \
	"pydantic_numpy>=9" "fastapi<0.150" \
	-e "${QCSC_DIR}/algorithms/qcsc_workflow_utility" \
	-e "${QCSC_DIR}/algorithms/sbd[ray,qfw]"

# 5. ffsim's wheel must run on this CPU. On some aarch64 hosts it does not
#    (Illegal instruction), and the tutorial's remedy is a source build.
ffsim_ok() {
	# A subshell, so that a crash is not announced by this shell.
	(
		"${PREFECT_VENV}/bin/python" - <<'PY'
import ffsim
norb, nelec = 4, (2, 2)
ffsim.apply_orbital_rotation(ffsim.hartree_fock_state(norb, nelec),
                             ffsim.random.random_orthogonal(norb, seed=0),
                             norb, nelec)
PY
	) >/dev/null 2>&1
}
if ! ffsim_ok; then
	version="$(uv pip show --python "${PREFECT_VENV}" ffsim 2>/dev/null |
		awk '/^Version:/ { print $2 }')"
	say "ffsim ${version} does not run here; rebuilding it from source"
	# The image's cargo registry is root-owned; build against a private one.
	CARGO_HOME="${HOME}/.cargo" \
	uv pip install --quiet --python "${PREFECT_VENV}" --reinstall --no-deps \
		--no-binary ffsim "ffsim==${version}"
	ffsim_ok || { say "ffsim still fails after the source build"; exit 1; }
fi

# 6. The native SBD solver, built by the repository's own Slurm script with
#    the image's OpenMPI and OpenBLAS.
native="${QCSC_DIR}/algorithms/sbd/native"
if [[ ! -x "${native}/diag" ]]; then
	say "building the SBD solver"
	if ! (cd "${native}" && bash build_sbd_slurm.sh >"${native}/build.log" 2>&1); then
		cat "${native}/build.log"
		exit 1
	fi
fi
say "SBD solver: ${native}/diag"

# 7. Verify the venv under the QFw activation the recipe uses with it.
export QFW_RUN_BASE_DIR="${QFW_RUN_BASE_DIR:-${HOME}/qfw-runs}"
export DEFW_LOG_LEVEL="${DEFW_LOG_LEVEL:-error}"
export DEFW_PY_LOGLEVEL="${DEFW_PY_LOGLEVEL:-critical}"
mkdir -p "${QFW_RUN_BASE_DIR}"
(
	set +u
	# shellcheck disable=SC1091
	source "${PREFIX_DIR}/bin/qfw-activate" --venv "${PREFECT_VENV}"
	python - <<'PY'
import importlib

for name in ("prefect", "ray", "ffsim", "pyscf", "qiskit_addon_sqd",
             "qcsc_prefect_executor", "sbd.main", "defw", "svc_lib_qpm"):
    importlib.import_module(name)
from importlib.metadata import version

print("qfw-prefect: verified prefect %s, ray %s, ffsim %s, qiskit %s"
      % (version("prefect"), version("ray"), version("ffsim"),
         version("qiskit")))
PY
)
say "done"
INNER
