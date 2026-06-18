#!/bin/sh
#
#SBATCH --job-name=shim-smoke
#SBATCH --output=shim-smoke.%J.out
#SBATCH --time=00:01:00
#SBATCH --partition=quantum
#SBATCH --nodes=1
#SBATCH --gres=qpu:1
#
# Smoke test for the QRMI/QDMI bifurcation service (services/svc_lib_qpm) —
# QFw's own parallel front-end implementation, alongside the untouched native
# svc_iqm_qpm. Confirms inside a SLURM-launched process that:
#   - svc_lib_qpm imports (frontend, drivers, descriptor, svc_qrc)
#   - routing is DESCRIPTOR-DRIVEN and PER-RESOURCE:
#       * IQM q20 (qrmi+qdmi): introspection is composable -- both QRMI (via
#         target()) and QDMI serve it; the descriptor preference (default QDMI)
#         / env override breaks the tie. Execution -> QRMI (reservation owner).
#       * a QRMI-only resource: introspection is served by QRMI; a call no
#         wired library covers -> NOT_IMPLEMENTED (the gap map)
#   - svc_qrc.QRC builds the Frontend from the resolved descriptor
# No real QRMI/QDMI hardware calls are made (drivers lazy-import their libs).

set -e

echo "[`date`] shim-smoke on `hostname`"

source /opt/qfw/qhpc/QFw/setup/qfw_activate
source "${QFW_IMAGE_VENV}/bin/activate"

python - <<'PY'
import os
from svc_lib_qpm.frontend import Frontend, NotImplementedByLibrary
from svc_lib_qpm.drivers import QrmiDriver, QdmiDriver
from svc_lib_qpm.descriptor import resolve_descriptor
from svc_lib_qpm.svc_qrc import QRC

print("[shim-smoke] imported frontend + drivers + descriptor + QRC: OK")

# --- Resource A: IQM q20, both libraries wired ---
desc = resolve_descriptor("ornl-iqm-20q")
fe = Frontend([QrmiDriver(desc), QdmiDriver(desc)], desc)

def check(call, expected):
    got = fe.route(call).name
    assert got == expected, f"{call}: routed to {got}, expected {expected}"
    print(f"[shim-smoke] [iqm-q20]  {call:26s} -> {got}")

check("get_device_info", "qdmi")          # composable (qdmi+qrmi); QDMI preferred
check("get_coupling_graph", "qdmi")       # composable (qdmi+qrmi); QDMI preferred
check("get_calibration_snapshot", "qdmi")
check("run_circuit", "qrmi")              # execution -> QRMI (reservation owner)
check("get_last_job_metadata", "qrmi")
check("get_backend_info", "qdmi")         # composable; descriptor preference=qdmi

# env preference overrides the descriptor preference; introspection is
# composable, so it flips to QRMI too (confirming QRMI serves introspection)
os.environ["QFW_QPU_IFACE_PREF"] = "qrmi"
fe2 = Frontend([QrmiDriver(desc), QdmiDriver(desc)], desc)
assert fe2.route("get_backend_info").name == "qrmi", "env preference not honored"
assert fe2.route("get_device_info").name == "qrmi", "introspection not composable"
print("[shim-smoke] QFW_QPU_IFACE_PREF=qrmi -> get_backend_info + "
      "get_device_info route to qrmi")
del os.environ["QFW_QPU_IFACE_PREF"]

# --- Resource B: a QRMI-only deployment (IBM Heron) ---
# QRMI serves introspection too (via target()), so device info / coupling
# resolve to QRMI here. The honest gap-map / NOT_IMPLEMENTED case is a call
# this deployment wires no capable library for (calibration below).
heron = {
    "id": "ibm-heron-r2", "provider": "ibm",
    "libraries": ["qrmi"], "preference": "qrmi", "execution_owner": "qrmi",
    "caps": {
        "get_device_info": ["qrmi"], "get_coupling_graph": ["qrmi"],
        "get_backend_info": ["qrmi"], "run_circuit": ["qrmi"],
        "get_last_job_timing": ["qrmi"], "get_last_job_metadata": ["qrmi"],
        # no calibration-capable library wired -> calibration is a gap here
    },
}
fe_h = Frontend([QrmiDriver(heron)], heron)
assert fe_h.route("run_circuit").name == "qrmi"
assert fe_h.route("get_device_info").name == "qrmi"
assert fe_h.route("get_coupling_graph").name == "qrmi"
print("[shim-smoke] [ibm-heron] introspection (device_info/coupling) -> qrmi "
      "(QRMI-only resource still introspects)")
try:
    fe_h.route("get_calibration_snapshot")
    raise SystemExit("expected NOT_IMPLEMENTED for get_calibration_snapshot")
except NotImplementedByLibrary:
    print("[shim-smoke] [ibm-heron] get_calibration_snapshot -> NOT_IMPLEMENTED "
          "(gap map: no calibration-capable library wired)")

# --- QRC builds the Frontend from the resolved descriptor ---
qrc = QRC(start=False)
print("[shim-smoke] QRC constructed from descriptor:          OK")
print("[shim-smoke] per-resource capability map:")
for call, libs in qrc.capability_map().items():
    print(f"             {call:26s} {libs}")
print()
print("SHIM BIFURCATION SMOKE: PASS")
PY

echo "[`date`] shim-smoke done on `hostname`"
