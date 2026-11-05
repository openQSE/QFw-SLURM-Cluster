"""Use QFw QPMs from PyCOMPSs tasks.

``qfw-compss-launch`` captures a :class:`QFwSession` for the Slurm job and
starts COMPSs. A task opens a :class:`QFwClient`, which loads that session, and
uses its Qiskit estimator or sampler; the client runs QFw in a ``defw-python``
child for as long as it is open.
"""

from .client import QFwClient, QFwError, QFwEstimator, QFwSampler
from .session import QFwSession

__all__ = ["QFwClient", "QFwError", "QFwEstimator", "QFwSampler",
		   "QFwSession"]
