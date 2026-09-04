# Start the Site-owned IQM QPM

Use this debugging recipe when only the directory service and persistent IQM
QPMd are needed. For ordinary operation, prefer
[Start all site services](start-all-site-services.md).

## Prepare Credentials

Before accepting hardware reservations, use the site's secret-management
workflow to populate this protected file on `iqm-head`:

```text
/etc/openqse/qfw/device/qpu-users.json
```

The records for `user-a`, `user-b`, and `user-c` must remain enabled and have
a non-empty `api_key` for `ornl-iqm-20q`. Keep the file owned by `root:root`
with mode `0600`. Do not print the file while validating it.

## Start the Directory Service

Enter `slurmctld` as root from the Docker host:

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

Run `man 1 qfw-dir-svc` for directory lifecycle details.

## Start IQM

Enter the IQM service node as root:

```bash
./do_ssh.sh iqm-head
```

Then run:

```bash
export QFW_SHARED_ROOT=/workspace/qfw-container-base
export QFW_SITE_CONFIG=/etc/openqse/qfw/site.yaml

source /opt/openqse/qfw/bin/qfw-activate \
  --venv /opt/openqse/qfw-venv

qfw-qpm-svc start \
  --scope site \
  --run-dir /var/lib/qfw-site-services/qpm/iqm-ornl-20q \
  --site-config "${QFW_SITE_CONFIG}" \
  --service-id iqm-ornl-20q \
  --timeout 300

qfw-qpm-svc status \
  --run-dir /var/lib/qfw-site-services/qpm/iqm-ornl-20q
qfw-deactivate
```

Run `man 1 qfw-qpm-svc` for lifecycle details. Credentials remain on
`iqm-head`; neither startup nor reservation exports them to application nodes.

## Stop IQM

On `iqm-head`:

```bash
source /opt/openqse/qfw/bin/qfw-activate \
  --venv /opt/openqse/qfw-venv
qfw-qpm-svc stop \
  --run-dir /var/lib/qfw-site-services/qpm/iqm-ornl-20q
qfw-deactivate
```

Stop the directory separately only when no other QPMd uses it.
