# Run a Guarded IQM Job

This recipe performs the validated short chemistry test against the persistent
real-IQM QPMd. Hardware runs must be explicitly authorized by the operator.

## Prerequisites

- The cluster, directory service, IQM QPMd, and gateway are ready.
- The protected `qpu-users.json` record for the selected user is enabled and
  contains a real API key.
- The operator has approved a five-qubit, 16-shot hardware run.
- `/workspace/qfw-container-base/chemistry_example_aim2` is available.

See [Start all site services](start-all-site-services.md) or
[Start the IQM QPM](start-iqm-qpm.md).

## Allocate the IQM Resource

From the Docker host:

```bash
cd /path/to/QFw-SLURM-Cluster
./do_ssh.sh --user user-a
```

Inside `slurmctld`:

```bash
salloc --partition=normal \
  --nodes=1 \
  --ntasks=1 \
  --time=00:20:00 \
  --qpu=ornl-iqm-20q \
  --workload-kind=hybrid \
  --circ-count=1 \
  --max-qubits=5 \
  --max-depth=1000 \
  --max-shots=16
```

Run `man 7 qfw-slurm` for allocation-time QPM requirements.

## Run the Chemistry Test

Inside the granted allocation:

```bash
source "${QFW_INSTALL_PREFIX}/bin/qfw-activate" \
  --venv "${QFW_VENV}"

cd "${QFW_SHARE_DIR}/examples"
./qfw_iqm_chem_driver.sh \
  --backend iqm \
  --target-device ornl-iqm-20q \
  --site-config "${QFW_SITE_CONFIG}" \
  --chem-app-dir /workspace/qfw-container-base/chemistry_example_aim2 \
  --shots 16 \
  --reservation-qubits 5 \
  example_1_He_from_pyscf.py --smoke --no-draw

qfw-deactivate
exit
```

Run `man 1 qfw_iqm_chem_driver.sh` for the driver's bounds and evidence files.
Success requires a terminal driver record with `status: ok`, chemistry
completion output, and subsequent release of the scheduler-owned reservation.

## Security Check

The application must not receive the API key. Inspect only non-secret service
and allocation state:

```bash
source "${QFW_INSTALL_PREFIX}/bin/qfw-activate" \
  --venv "${QFW_VENV}"
qfw-sinfo iqm-head
qfw-squeue
qfw-deactivate
```

Do not print the protected device directory or copy it into the user's run
directory.
