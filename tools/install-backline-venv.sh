#!/bin/bash
# Create the shared Backline venv used by the backline-local QPM and by Backline
# applications. Run once inside any cluster container (the volume is shared):
#
#   docker exec slurmctld /mnt/../tools/install-backline-venv.sh   # or ./do_ssh.sh, then run it
#
# The venv must use the same Python as the QFw venv (3.12 on the Rocky 10 image):
# applications run through qfw-srun, whose embedded DEFw interpreter checks this.
set -euo pipefail

venv="${BACKLINE_VENV:-/workspace/qfw-container-base/backline-venv}"
python="${PYTHON:-python3}"
release="https://github.com/PennyLaneAI"

"${python}" -c 'import sys; assert sys.version_info >= (3, 12), "Catalyst 0.16 wheels need Python 3.12+"'
"${python}" -m venv "${venv}"
"${venv}/bin/pip" install -q --upgrade pip
"${venv}/bin/pip" install -q pennylane-catalyst==0.16.0b1 \
	-f "${release}/pennylane/releases/expanded_assets/v0.46.0b1" \
	-f "${release}/pennylane-lightning/releases/expanded_assets/v0.46.0b1" \
	-f "${release}/catalyst/releases/expanded_assets/v0.16.0b1"
# DEFw's client-side imports, for applications that reach QFw services.
"${venv}/bin/pip" install -q PyYAML "jsonschema>=4" netifaces psutil paramiko rich

lib="$("${venv}/bin/python" -c 'import importlib.util, pathlib; print(pathlib.Path(list(importlib.util.find_spec("catalyst").submodule_search_locations)[0]) / "lib")')"
test -f "${lib}/libsteane_coprocessor_cpu.so"
# The demo program, on the shared volume so jobs on any compute node can run it.
# Jobs run this code, we check out a fixed commit. QRI_BACKLINE_REF overrides it.
# TODO: move the demo under openQSE.
demo="${QRI_BACKLINE_DIR:-/workspace/qfw-container-base/qri-backline}"
demo_ref="${QRI_BACKLINE_REF:-fea211a3d9e282c70e37672e6cdf1d679b372000}"
if [ ! -d "${demo}/.git" ]; then
	git clone -q https://github.com/josephleekl/qri-backline "${demo}"
	git -C "${demo}" checkout -q "${demo_ref}"
fi
echo "backline venv ready: ${venv} (decoders in ${lib})"
