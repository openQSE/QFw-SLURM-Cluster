# Run a Heterogeneous NWQSim Job

This recipe creates two classical Slurm components and one allocation-wide
NWQSim reservation. The persistent directory, DVM, and QPMd remain outside
both application components.

## Prerequisites

- Complete [Start all site services](start-all-site-services.md).
- Enter the controller as a non-root test user.

```bash
cd /path/to/QFw-SLURM-Cluster
./do_ssh.sh --user user-a
```

## Allocate Both Components

Put the quantum options on heterogeneous group 0, which runs the application:

```bash
salloc --partition=normal --nodes=1 --ntasks=1 --time=00:15:00 \
  --qpu=nwqsim \
  --workload-kind=hybrid \
  --circ-count=1 \
  --max-qubits=5 \
  --max-depth=20 \
  --max-shots=1024 \
  : --partition=normal --nodes=1 --ntasks=1 --time=00:15:00
```

Run `man 7 qfw-slurm` and `man salloc` for the QPM and heterogeneous option
contracts. Slurm grants the complete heterogeneous allocation only after QPMd
accepts the final reservation.

## Run in Group 0

```bash
source "${QFW_INSTALL_PREFIX}/bin/qfw-activate" \
  --venv "${QFW_VENV}"

cd "${QFW_SHARE_DIR}/examples"
qfw-setup --site-config "${QFW_SITE_CONFIG}"
qfw-srun --het-group 0 tests/test_qiskit_simple.py 5 nwqsim
```

Run `man 1 qfw-setup`, `man 1 qfw-srun`, and `man 1 qfw-teardown` for the
application lifecycle. In site mode, `qfw-setup` connects to the existing
directory and does not start another QPMd.

## Verify Both Groups

Before teardown, these commands should print the same compact tuple set:

```bash
srun --het-group=0 /bin/sh -c \
  'printf "%s\n" "${QFW_RESERVATIONS}"'
srun --het-group=1 /bin/sh -c \
  'printf "%s\n" "${QFW_RESERVATIONS}"'
```

## Clean Up

```bash
qfw-teardown
qfw-deactivate
exit
```

Exiting the allocation releases the one allocation-wide QPM reservation.
