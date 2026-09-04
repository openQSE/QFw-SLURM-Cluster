# Inspect and Recover QFw Services

Use this recipe when an allocation is pending, a QPM appears unavailable, or
a previous service lifecycle did not finish cleanly.

## Inspect Slurm

Enter `slurmctld` as root:

```bash
cd /path/to/QFw-SLURM-Cluster
./do_ssh.sh
sinfo -N -o '%N %P %t %f %c'
squeue -o '%i %u %T %R %N'
```

Application nodes should be in `normal`. The four dedicated service nodes
should be in `qfw-services`, not allocated to application jobs.

## Inspect the Service Plane

```bash
qfw-site-services status
```

Run `man 8 qfw-site-services` for state and exit-status details. For the
directory or one QPM manager, activate QFw on its owning node and inspect the
private run directory:

```bash
source /opt/openqse/qfw/bin/qfw-activate \
  --venv /opt/openqse/qfw-venv

qfw-dir-svc status --run-dir /var/lib/qfw-site-services/directory
qfw-qpm-svc status --run-dir /var/lib/qfw-site-services/qpm/nwqsim
qfw-qpm-svc status \
  --run-dir /var/lib/qfw-site-services/qpm/iqm-ornl-20q

qfw-deactivate
```

Run `man 1 qfw-dir-svc` and `man 1 qfw-qpm-svc` before changing manager state.
The directory command belongs on `slurmctld`; each QPM command belongs on its
QPM host.

## Inspect as an Application User

```bash
./do_ssh.sh --user user-a
source "${QFW_INSTALL_PREFIX}/bin/qfw-activate" \
  --venv "${QFW_VENV}"

qfw-sinfo
qfw-sinfo nwqsim-head
qfw-sinfo iqm-head
qfw-squeue

qfw-deactivate
```

Run `man 1 qfw-sinfo` and `man 1 qfw-squeue` for JSON output and filtering.
These commands expose sanitized service and allocation state, not provider
credentials or other users' reservation IDs.

## Recover the Complete Service Plane

Do not delete lifecycle files by hand. The managers distinguish ready,
starting, stopped, and stale state and preserve useful diagnostics.

From `slurmctld` as root:

```bash
qfw-site-services stop
qfw-site-services start
qfw-site-services status
```

If startup still fails, inspect the manager logs beneath the corresponding
run directory:

```text
/var/lib/qfw-site-services/directory/services/qfw-site-dirsvc/logs
/var/lib/qfw-site-services/qpm/nwqsim/services/nwqsim/logs
/var/lib/qfw-site-services/qpm/iqm-ornl-20q/services/iqm-ornl-20q/logs
```

For a pending job, inspect `scontrol show job <job-id>` and the gateway log at
`/var/log/qfw-slurm-gateway/gateway.log`. `BurstBufferResources` is expected
while Slurm polls a delayed preliminary evaluation. Cancel the job with
`scancel <job-id>` when the user no longer wants the allocation; the teardown
path attempts reservation release.
