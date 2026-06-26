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
#   - Device Introspection (design doc section 13): the QDMI -> qhw adapter
#     normalizes a device topology into schema-valid qhw-device-v1 /
#     qhw-coupling-v1 records (qhw-data runs real jsonschema validation)
# Routing and normalization run with no credentials. With QPU creds set
# (QFW_QC_URL + QFW_API_KEY) it also runs real introspection through QDMI AND
# QRMI and confirms they yield the same qhw shape (the QRMI leg is best-effort:
# it needs QRMI's resource env, set by the SPANK plugin inside a reservation).

set -e

echo "[`date`] shim-smoke on `hostname`"

source /opt/qfw/qhpc/QFw/setup/qfw_activate
source "${QFW_IMAGE_VENV}/bin/activate"

# The sourced env scripts disable errexit; re-enable it so a failing assertion in
# the Python block below fails the job (otherwise SLURM reports COMPLETED 0:0).
set -e

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

# --- Device Introspection (design doc section 13): backend -> qhw normalization
# Exercise the shared BackendV2 -> qhw adapter (used by both the QDMI and QRMI
# drivers) with a synthetic device topology (no hardware or credentials).
# Proves get_device_info / get_coupling_graph yield schema-valid,
# provider-neutral qhw records in-container (qhw-data runs real jsonschema
# validation here).
from svc_lib_qpm.drivers.backend_normalize import (
    extract_topology, to_coupling_record, to_device_record)

class _FakeCouplingMap:
    def __init__(self, edges):
        self._edges = edges
    def get_edges(self):
        return list(self._edges)

class _FakeTarget:
    def __init__(self, loci):
        self._loci = loci
    @property
    def operation_names(self):
        return list(self._loci)
    def __getitem__(self, name):
        return self._loci[name]

class _FakeBackend:
    # Minimal duck-typed Qiskit BackendV2: a 4-qubit line, r/cz/measure.
    num_qubits = 4
    coupling_map = _FakeCouplingMap([(0, 1), (1, 0), (1, 2), (2, 3)])
    target = _FakeTarget({
        "r":       {(0,): 1, (1,): 1, (2,): 1, (3,): 1},
        "cz":      {(0, 1): 1, (1, 2): 1, (2, 3): 1},
        "measure": {(0,): 1, (1,): 1, (2,): 1, (3,): 1},
    })

topo = extract_topology(_FakeBackend())
assert topo["num_qubits"] == 4
assert topo["edges"] == [["0", "1"], ["1", "2"], ["2", "3"]], topo["edges"]

dev = to_device_record(topo, "iqm", "ornl-iqm-20q")     # validate=True (schema)
cpl = to_coupling_record(topo, "iqm", "ornl-iqm-20q")   # validate=True (schema)
assert dev["schema"] == "qhw-device-v1" and len(dev["qubits"]) == 4
assert cpl["schema"] == "qhw-coupling-v1"
assert cpl["coupling"]["edges"] == [["0", "1"], ["1", "2"], ["2", "3"]]
_ops = {o["name"]: o["arity"] for o in cpl["operations"]}
assert _ops.get("cz") == 2 and _ops.get("r") == 1
print("[shim-smoke] backend->qhw normalization: device(%d qubits) + "
      "coupling(%d edges, %d ops), schema-valid"
      % (len(dev["qubits"]), len(cpl["coupling"]["edges"]),
         len(cpl["operations"])))

# --- Device Introspection via the RAW passthrough (section 13) ----------------
# The QDMI driver now prefers QDMI-on-IQM's raw_device_config()
# (QDMI_DEVICE_PROPERTY_CUSTOM1) and feeds the raw IQM payload to qhw-iqm -- the
# SAME normalizer the QRMI driver and native path use -- so both libraries yield
# one identical qhw shape carrying IQM "QB" qubit ids (not 0..n-1). Exercise that
# path with no hardware/creds by injecting a fake backend whose
# raw_device_config() returns a synthetic IQM payload; then confirm the guarded
# fallback to backend_normalize when raw_device_config is absent.
_RAW_IQM = {
    "static_quantum_architecture": {
        "dut_label": "smoke-q3",
        "qubits": ["QB1", "QB2", "QB3"],
        "connectivity": [["QB1", "QB2"], ["QB2", "QB3"]],
    },
    "dynamic_quantum_architecture": {
        "calibration_set_id": "smoke-cal",
        "qubits": ["QB1", "QB2", "QB3"],
        "gates": {
            "prx": {"default_implementation": "drag",
                    "implementations": {"drag": {"loci": [["QB1"], ["QB2"], ["QB3"]]}}},
            "cz": {"default_implementation": "tgss",
                   "implementations": {"tgss": {"loci": [["QB1", "QB2"], ["QB2", "QB3"]]}}},
        },
    },
    "quality_metrics": {},
    "calibration_set_id": "smoke-cal",
}

class _RawBackend:
    def raw_device_config(self):
        return dict(_RAW_IQM)

drv_raw = QdmiDriver(desc)
drv_raw._backend_obj = _RawBackend()  # inject; bypass live IQMBackend construction
rdev = drv_raw.get_device_info()
rcpl = drv_raw.get_coupling_graph()
assert rdev["schema"] == "qhw-device-v1", rdev.get("schema")
assert rcpl["schema"] == "qhw-coupling-v1", rcpl.get("schema")
assert [q["id"] for q in rdev["qubits"]] == ["QB1", "QB2", "QB3"], rdev["qubits"]  # IQM "QB" labels, not 0..n
assert len(rcpl["coupling"]["edges"]) == 2, rcpl["coupling"]["edges"]
_rops = {o["name"]: o["arity"] for o in rcpl["operations"]}
assert _rops.get("cz") == 2 and _rops.get("prx") == 1, _rops
print("[shim-smoke] QDMI raw passthrough -> qhw-iqm: device(%d qubits %s) + "
      "coupling(%d edges, %d ops)"
      % (len(rdev["qubits"]), [q["id"] for q in rdev["qubits"]],
         len(rcpl["coupling"]["edges"]), len(rcpl["operations"])))

# Guarded fallback: a backend WITHOUT raw_device_config() must fall back to the
# Qiskit-Target normalizer (backend_normalize), yielding integer qubit ids.
class _NoRawBackend:
    num_qubits = 4
    coupling_map = _FakeCouplingMap([(0, 1), (1, 2), (2, 3)])
    target = _FakeTarget({
        "r": {(0,): 1, (1,): 1}, "cz": {(0, 1): 1}, "measure": {(0,): 1}})

drv_fb = QdmiDriver(desc)
drv_fb._backend_obj = _NoRawBackend()
assert drv_fb._iqm_raw() is None  # no raw_device_config -> fallback signal
fdev = drv_fb.get_device_info()
assert fdev["schema"] == "qhw-device-v1" and \
    [q["id"] for q in fdev["qubits"]] == ["0", "1", "2", "3"]
print("[shim-smoke] QDMI fallback (no raw_device_config) -> backend_normalize: OK")

# --- Optional live check: real hardware introspection when creds present ------
# With QPU credentials, run get_device_info / get_coupling_graph against the real
# device through EACH library and confirm they produce the same provider-neutral
# qhw shape -- the whole point of the shim. QDMI uses QFW_QC_URL / QFW_API_KEY;
# QRMI uses its own resource env (set by the SPANK plugin inside a reservation),
# so the QRMI leg is best-effort and skips cleanly when that env is absent.
def _live_introspect(pref):
    os.environ["QFW_QPU_IFACE_PREF"] = pref
    try:
        f = Frontend([QrmiDriver(desc), QdmiDriver(desc)], desc)
        used = f.route("get_device_info").name
        dev = f.get_device_info()
        cpl = f.get_coupling_graph()
        assert dev["schema"] == "qhw-device-v1", dev.get("schema")
        assert cpl["schema"] == "qhw-coupling-v1", cpl.get("schema")
        return used, dev, cpl
    finally:
        os.environ.pop("QFW_QPU_IFACE_PREF", None)

if os.environ.get("QFW_QC_URL") and os.environ.get("QFW_API_KEY"):
    # QDMI leg -- explicit opt-in via QFW_QC_URL/QFW_API_KEY; failures are real.
    qused, qdev, qcpl = _live_introspect("qdmi")
    print("[shim-smoke] live %s -> qhw-device-v1 (%d qubits) + qhw-coupling-v1 "
          "(%d edges)" % (qused, len(qdev["qubits"]),
                          len(qcpl["coupling"]["edges"])))
    # QRMI leg -- best-effort; needs QRMI's reservation env.
    try:
        rused, rdev, rcpl = _live_introspect("qrmi")
    except Exception as exc:
        print("[shim-smoke] live QRMI introspection: unavailable (%s) -- needs "
              "QRMI resource env (SPANK reservation)" % type(exc).__name__)
    else:
        print("[shim-smoke] live %s -> qhw-device-v1 (%d qubits) + qhw-coupling-v1 "
              "(%d edges)" % (rused, len(rdev["qubits"]),
                              len(rcpl["coupling"]["edges"])))
        # Cross-library consistency: one qhw shape regardless of the source.
        assert qdev["schema"] == rdev["schema"]
        assert len(qdev["qubits"]) == len(rdev["qubits"]), \
            "QDMI vs QRMI qubit count differs"
        assert (len(qcpl["coupling"]["edges"])
                == len(rcpl["coupling"]["edges"])), \
            "QDMI vs QRMI edge count differs"
        print("[shim-smoke] cross-library: QDMI and QRMI agree on qhw shape "
              "(%d qubits, %d edges)" % (len(qdev["qubits"]),
                                         len(qcpl["coupling"]["edges"])))
else:
    print("[shim-smoke] live introspection: skipped "
          "(set QFW_QC_URL + QFW_API_KEY to enable)")

print()
print("SHIM BIFURCATION + INTROSPECTION SMOKE: PASS")
PY

echo "[`date`] shim-smoke done on `hostname`"
