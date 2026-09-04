# Start All Site-owned QFw Services

This is the canonical administrator workflow. It starts the directory service
on `slurmctld`, a three-node NWQSim DVM and QPMd, and the IQM QPMd. The QPMd
service nodes remain outside application allocations.

## Prerequisites

- Complete [Build and start the cluster](build-and-start-cluster.md).
- Run as root in `slurmctld`.
- Before accepting real-IQM reservations, populate
  `/etc/openqse/qfw/device/qpu-users.json` on `iqm-head` through the approved
  secret-management workflow. Keep it owned by `root:root` with mode `0600`.

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
ordered and failure-safe. If a QPM fails to start, the command removes only
components started by that invocation.

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

Run `man 1 qfw-sinfo` for the service columns. NWQSim and IQM should report
`IDLE`; NWQSim should identify all three assigned simulator hosts and a ready
DVM.

## Stop

```bash
qfw-site-services stop
```

The stop action removes the IQM QPM, NWQSim QPM and DVM, and directory service
in dependency order. It does not stop the Slurm cluster.
