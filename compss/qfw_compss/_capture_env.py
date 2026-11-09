"""Write this process's environment to a JSON file.

``QFwSession.capture`` runs it as ``qfw-srun ... -- _capture_env.py OUT``, so
the environment it writes is the one QFw gives an application.
"""

import json
import os
import sys
from pathlib import Path


def main():
	out = Path(sys.argv[1])
	tmp = out.with_suffix(".tmp")
	tmp.write_text(json.dumps(dict(os.environ)))
	os.chmod(tmp, 0o600)
	tmp.rename(out)


if __name__ == "__main__":
	main()
