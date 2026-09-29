# Start All Site-owned QFw Services

This is the canonical administrator workflow. It starts the directory service
on `slurmctld`, a three-node NWQSim DVM and QPMd, the IQM QPMd, IQM shim QPMd,
IBM shim QPMd, AWS QPMd, fake IQM QPMd, and QFw Slurm gateway. The QPMd
service nodes remain outside application allocations.

## Prerequisites

- Complete [Build and start the cluster](build-and-start-cluster.md).
- Run as root in `slurmctld`.
- Before accepting real-device reservations, populate the IQM, IBM, and AWS entries
  in `/etc/openqse/qfw/device/qpu-users.json` on their QPM nodes through the
  approved secret-management workflow. IBM entries require an API key and
  service CRN. AWS entries require the credentials expected by AWS QDMI. Keep
  the file owned by `root:root` with mode `0600`.
- Do not accept AWS reservations until the shim can bind the reservation's
  selected target to an AWS-QDMI device session. The cluster advertises
  `aws-ionq-aria-1` and `aws-rigetti-ankaa`, but the current shim remains
  single-target.

The packaged credential file intentionally contains empty API keys. Never put
a real key in the repository, image, shell command line, or application
environment.

## Start

From the Docker host:

```bash
cd /path/to/QFw-SLURM-Cluster
./do_ssh.sh
```

Inside `slurmctld`:

```bash
qfw-site-services start
qfw-site-services status
```

Run `man 8 qfw-site-services` for command details. Startup is dependency
ordered and failure-safe: directory, NWQSim, IQM, IQM shim, IBM shim, AWS,
fake IQM, then gateway. If a component fails to start, the command removes
only components started by that invocation.

## Verify

```bash
export QFW_SHARED_ROOT=/workspace/qfw-container-base
export QFW_SIMULATOR_NODES=nwqsim-head,nwqsim-worker-1,nwqsim-worker-2

source /opt/openqse/qfw/bin/qfw-activate \
  --venv /opt/openqse/qfw-venv

qfw-sinfo
qfw-sinfo --json
qfw-deactivate
```

Run `man 1 qfw-sinfo` for the service columns. Configured services should
report `IDLE`; NWQSim should identify all three assigned simulator hosts and a
ready DVM.

## Stop

```bash
qfw-site-services stop
```

The stop action first closes the gateway to new reservations, then removes the
managed QPMs, NWQSim DVM, and directory service. It does not stop the Slurm
cluster.
