# QFw Slurm Cluster Recipes

These recipes are the primary entry points for building, administering, and
using the virtual QFw Slurm cluster.

| Goal | Recipe |
| --- | --- |
| Build and start the cluster | [Build and start the cluster](build-and-start-cluster.md) |
| Start the complete site service plane | [Start all site services](start-all-site-services.md) |
| Start only the directory and NWQSim QPMd | [Start the NWQSim QPM](start-nwqsim-qpm.md) |
| Start only the directory and IQM QPMd | [Start the IQM QPM](start-iqm-qpm.md) |
| Run a normal NWQSim application job | [Run an NWQSim job](run-nwqsim-job.md) |
| Run a guarded real-IQM application job | [Run an IQM job](run-iqm-job.md) |
| Run a heterogeneous application job | [Run a heterogeneous NWQSim job](run-heterogeneous-nwqsim-job.md) |
| Inspect and recover the cluster | [Inspect and recover services](inspect-and-recover-services.md) |

The commands assume the image-contained installations:

```text
QFw:       /opt/openqse/qfw
Python:    /opt/openqse/qfw-venv
qfw-slurm: /opt/openqse/qfw-slurm
```

The cluster provides `user-a`, `user-b`, and `user-c` as non-root application
users. Site directory, DVM, QPMd, and credential state remain root-owned.

Use `man 8 qfw-site-services` for the cluster service-plane command,
`man 7 qfw-slurm` for allocation options, and `man 7 qfw-examples` for the
installed application examples.
