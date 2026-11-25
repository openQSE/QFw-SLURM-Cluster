# Backline QPM (`backline-local`)

`backline-local` is a client-executed QPM (QFw `services/svc_backline_qpm`). A
reservation picks a Backline controller, QEC decoder coprocessor and
transport from the site inventory; the application reads that placement and runs its
PennyLane/Catalyst program on it. It never sends circuits through QRI.

It runs on `qec-backline-head` and is opt-in: `qfw-site-services start` (target `all`) does not
start it.

## Set up once

The Backline QPM is in [openQSE/QFw](https://github.com/openQSE/QFw). The image keeps its
stock QFw; the Backline QPM runs from a development override built from QFw `main` (see
"Build and use a development QFw override" in the README).

On the host:

```bash
git clone https://github.com/openQSE/QFw-SLURM-Cluster
cd QFw-SLURM-Cluster
SHARED=/path/to/shared-dir
./do_configure.sh --prefix "$SHARED"
git clone --recursive https://github.com/openQSE/QFw "$SHARED/QFw"
./do_build.sh
./do_startup.sh
./do_qfw_build.sh --clean                     # the override, in $SHARED/qfw-install
```

In the cluster:

```bash
./do_ssh.sh                                   # into the cluster, as root
/path/to/QFw-SLURM-Cluster/tools/install-backline-venv.sh   # shared venv: Catalyst 0.16.0b1 wheels
qfw-site-services start                       # directory, gateway and the default QPMs
export QFW_INSTALL_PREFIX=/workspace/qfw-container-base/qfw-install   # the override
qfw-site-services --target backline start
qfw-site-services --target backline status
```

The `backline` environment module (`modulefiles/backline`) points `CATALYST_LIB` at the
shared venv, so the QPM's inventory finds the precompiled decoders.

### On an existing cluster

On a cluster that is already set up, pull this, then run these in place of `./do_build.sh` and
`./do_startup.sh` above; `./do_qfw_build.sh --clean` and the in-cluster steps are unchanged:

```bash
./do_build.sh                       # modulefiles/backline is copied into the image
./do_restart.sh --force-recreate    # recreate the containers from it, adding qec-backline-head
./do_startup.sh                     # refreshes slurm.conf in the etc_slurm volume, then provisions qec-backline-head
```

## Run a Backline program

The job script is `qri-backline/examples/job.sh`, cloned to
`/workspace/qfw-container-base/qri-backline` by `tools/install-backline-venv.sh`. Submit it
as a provisioned test user, not root (root batch jobs may take slurmd down on this
cluster). qfw-slurm requires a Slurm account (`-A`); the test users use `qfw-test`:

```bash
./do_ssh.sh --user user-a
sbatch -A qfw-test /workspace/qfw-container-base/qri-backline/examples/job.sh
```

The job makes two requests:

1. **Quantum resources.** The `#SBATCH --qpu=backline-local ...` lines. qfw-slurm reserves
   `backline-local`'s quantum budget while the job is allocated and passes the reservation to
   each step in `QFW_RESERVATIONS`. The allocation's teardown releases it.
2. **Classical QEC resources.** The program asks the QPM for them against that reservation
   (`reserve` with `for_reservation` and the `resource_intent` in
   `intents/cpu-steane-memcpy.yaml`: a CPU controller, a Steane decoder, memcpy). The QPM
   starts a `catalyst-executor` on `qec-backline-head` for the reservation and returns its
   address in the placement; the program compiles locally and runs controller and decoder
   there. The executor stops when the reservation ends.

`--max-qubits` counts logical qubits.

## Security

The `catalyst-executor` runs whatever compiled program a client sends it. It listens on
all interfaces and does not authenticate clients, so anyone who can reach its port can run
code as the user the QPM runs as, which is root on `qec-backline-head`. Use it only on a
trusted network until this is addressed.

## Files

| File | Role |
| --- | --- |
| `docker-compose.yml`, `slurm.conf`, `tools/provision-qfw-cluster.sh` | the `qec-backline-head` node |
| `config/site-services.yaml` | the `backline-local` service, loading the `backline` module |
| `config/device-access.yaml`, `config/qpu-users.json` | device record and user entitlement |
| `config/qfw-slurm/resources.lua`, `config/qfw-slurm/plugin.conf` | `--qpu=backline-local` |
| `modulefiles/backline`, `tools/install-backline-venv.sh` | the shared Backline venv and the demo checkout |
| `tools/qfw-site-services` | `--target backline` start, stop, status |
