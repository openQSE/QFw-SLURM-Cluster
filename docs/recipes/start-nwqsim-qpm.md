# Start the Site-owned NWQSim QPM

Use this debugging recipe when only the directory service and persistent
NWQSim QPMd are needed. For ordinary operation, prefer
[Start all site services](start-all-site-services.md).

## Start the Directory Service

From the Docker host, enter `slurmctld` as root:

```bash
cd /path/to/QFw-SLURM-Cluster
./do_ssh.sh
```

Inside `slurmctld`:

```bash
export QFW_SHARED_ROOT=/workspace/qfw-container-base
export QFW_SITE_CONFIG=/etc/openqse/qfw/site.yaml

source /opt/openqse/qfw/bin/qfw-activate \
  --venv /opt/openqse/qfw-venv

qfw-dir-svc status --run-dir /var/lib/qfw-site-services/directory || \
qfw-dir-svc start \
  --scope site \
  --run-dir /var/lib/qfw-site-services/directory \
  --site-config "${QFW_SITE_CONFIG}" \
  --timeout 300

qfw-deactivate
exit
```

Run `man 1 qfw-dir-svc` for directory lifecycle details. The command writes
the client-readable connection record beneath `${QFW_SHARED_ROOT}`.

## Start NWQSim

Enter the NWQSim head node as root:

```bash
./do_ssh.sh nwqsim-head
```

Then run:

```bash
export QFW_SHARED_ROOT=/workspace/qfw-container-base
export QFW_SITE_CONFIG=/etc/openqse/qfw/site.yaml
export QFW_SIMULATOR_NODES=nwqsim-head,nwqsim-worker-1,nwqsim-worker-2

source /opt/openqse/qfw/bin/qfw-activate \
  --venv /opt/openqse/qfw-venv

qfw-qpm-svc start \
  --scope site \
  --run-dir /var/lib/qfw-site-services/qpm/nwqsim \
  --site-config "${QFW_SITE_CONFIG}" \
  --service-id nwqsim \
  --timeout 300

qfw-qpm-svc status \
  --run-dir /var/lib/qfw-site-services/qpm/nwqsim
qfw-deactivate
```

Run `man 1 qfw-qpm-svc` for QPMd and DVM lifecycle details. The manager loads
the declared libfabric, Open MPI, and NWQSim modules automatically.

## Stop NWQSim

On `nwqsim-head`:

```bash
source /opt/openqse/qfw/bin/qfw-activate \
  --venv /opt/openqse/qfw-venv
qfw-qpm-svc stop \
  --run-dir /var/lib/qfw-site-services/qpm/nwqsim
qfw-deactivate
```

Stop the directory separately only when no other QPMd uses it.
