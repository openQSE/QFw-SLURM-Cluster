# Run an NWQSim Job

This recipe reserves persistent NWQSim capacity during `salloc`, then runs an
installed QFw example on an ordinary application node.

## Prerequisites

- The cluster is running.
- The site directory, NWQSim DVM, NWQSim QPMd, and qfw-slurm gateway are ready.
- The application uses one of the non-root test users.

See [Start all site services](start-all-site-services.md) or
[Start the NWQSim QPM](start-nwqsim-qpm.md).

## Allocate Quantum and Classical Resources

From the Docker host:

```bash
cd /path/to/QFw-SLURM-Cluster
./do_ssh.sh --user user-a
```

Inside `slurmctld`, request the QPM and bounded workload at allocation time:

```bash
salloc --partition=normal \
  --nodes=1 \
  --ntasks=1 \
  --time=00:10:00 \
  --qpu=nwqsim \
  --workload-kind=quantum \
  --circ-count=1 \
  --max-qubits=5 \
  --max-depth=20 \
  --max-shots=1024
```

Run `man 7 qfw-slurm` for allocator options. Do not pass these options to
`srun`; QPM reservation occurs before Slurm grants the allocation.

## Run the Application

Inside the granted allocation:

```bash
source "${QFW_INSTALL_PREFIX}/bin/qfw-activate" \
  --venv "${QFW_VENV}"

cd "${QFW_SHARE_DIR}/examples"
./qfw_qiskit_simple.sh \
  --service-mode site \
  --backend nwqsim \
  5

qfw-deactivate
exit
```

Run `man 1 qfw_qiskit_simple.sh`, `man 1 qfw-activate`, and
`man 1 qfw-deactivate` for command details. The example uses `qfw-srun`, whose
remote SPANK callback obtains `QFW_RESERVATIONS` from the gateway.

## Verify Release

After leaving the allocation:

```bash
source "${QFW_INSTALL_PREFIX}/bin/qfw-activate" \
  --venv "${QFW_VENV}"
qfw-sinfo nwqsim-head
qfw-squeue
qfw-deactivate
```

Run `man 1 qfw-sinfo` and `man 1 qfw-squeue` for output details. NWQSim should
return to `IDLE` after the allocation's best-effort release completes.
