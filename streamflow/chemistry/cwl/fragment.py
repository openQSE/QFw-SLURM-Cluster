#!/usr/bin/env python3

import json
import math
import os
from pathlib import Path
import sys
import traceback

sys.path.insert(0, os.environ["CHEMISTRY_ROOT"])
from chemapp_fcidump_workflow import calculate
from puccd import puccd_finalize, puccd_initialize


def main():
    fragment, backend, output, shots, macro, amplitude, orbital = sys.argv[1:]
    puccd_initialize(qfw=True, provider=backend, shots=int(shots))
    try:
        energy = calculate(fragment, int(macro), int(amplitude), int(orbital))
        if not math.isfinite(energy):
            raise ValueError("Fragment energy must be finite")
        Path(output).write_text(json.dumps({"fragment": Path(fragment).name,
                                           "backend": backend, "energy": energy}) + "\n")
    except Exception:
        traceback.print_exc()
        raise
    finally:
        puccd_finalize(qfw=True)


if __name__ == "__main__":
    main()
