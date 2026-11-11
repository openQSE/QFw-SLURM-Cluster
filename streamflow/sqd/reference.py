#!/usr/bin/env python3

import argparse
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path


def reference(path, state=None):
    from pyscf import fci
    from pyscf.tools import fcidump

    data = fcidump.read(str(path), verbose=False)
    electrons, orbitals = data["NELEC"], data["NORB"]
    determinants = math.comb(orbitals, electrons // 2) ** 2
    if electrons % 2 or data.get("MS2", data.get("MS", 0)) or determinants > 100000:
        raise ValueError("FCI verification supports small closed-shell cases only")
    solver = fci.direct_spin1.FCI()
    solver.conv_tol = 1e-12
    energy, _ = solver.kernel(data["H1"], data["H2"], orbitals, electrons, ecore=data["ECORE"])
    if not solver.converged:
        raise RuntimeError("FCI reference did not converge")
    result = dict(fcidump_sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                  pyscf_version=importlib.metadata.version("pyscf"), orbitals=orbitals, electrons=electrons,
                  determinants=determinants, ecore_hartree=data["ECORE"], fci_total_energy_hartree=float(energy))
    if state is not None:
        state = json.loads(Path(state).read_text())
        if state.get("fcidump_sha256") != result["fcidump_sha256"]:
            raise ValueError("The SQD result does not identify the same input FCIDUMP")
        energy = state["best_energy"]
        if not math.isfinite(energy):
            raise ValueError("Invalid SQD energy")
        result.update(sqd_total_energy_hartree=energy, absolute_error_hartree=abs(energy - result["fci_total_energy_hartree"]),
                      matches_fci_at_1e_8=abs(energy - result["fci_total_energy_hartree"]) < 1e-8)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("fcidump", type=Path)
    parser.add_argument("state", type=Path, nargs="?")
    args = parser.parse_args()
    print(json.dumps(reference(args.fcidump, args.state), indent=2, allow_nan=False))
