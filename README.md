# QFw Slurm Docker Cluster

This directory contains a Docker-based Slurm cluster that has been extended to
serve as a QFw and DEFw development and profiling environment.

The intent is to keep the heavy runtime stack inside the image and keep the
active QFw workspace on the host. That gives you:

- a repeatable Slurm test cluster
- a repeatable MPI/libfabric toolchain
- an image-contained QFw install that can run without a mounted checkout
- prebuilt QFw circuit runners for TNQVM and NWQ-Sim
- disposable containers
- host-persistent source, virtual environments, and build artifacts

## What This Image Contains

The image builds and installs these layers:

- Slurm
- system Python 3.12 from Rocky 10
- `environment-modules`
- system GCC toolchain from Rocky 10
- `libfabric`
- OpenMPI with the bundled PRRTE checkout
- OSU Micro-Benchmarks
- QFw under `/opt/qfw/qhpc/QFw`
- a QFw Python virtual environment under `/opt/qfw/qhpc/venv`
- QFw build and install artifacts under `/opt/qfw/qhpc/build/image` and
  `/opt/qfw/qhpc/install/image`
- prebuilt `circuit_runner.tnqvm` and `circuit_runner.nwqsim` on `PATH`
- QFw-facing convenience packages:
  - `cmake`
  - `gcc-gfortran`
  - `openblas-devel`
  - `swig`
  - `scons`

The image also installs runtime modulefiles for:

- `cmake`
- `openblas`
- `swig`
- `gcc-native/13.2`
- `gcc/13.2`
- `rocm`

The modulefiles are for interactive use inside the container. They are not used
to control Docker build correctness. The MPI stack is built with explicit GCC 13
environment variables in the Dockerfile.

The image-level runtime environment includes OpenMPI, libfabric, and the
image-contained QFw circuit runner paths in `PATH` and `LD_LIBRARY_PATH`.
Do not globally source `qfw_activate` from the image entrypoint; activation is
still an explicit shell action because it rewires the QFw Python environment.

## Cluster Topology

`docker-compose.yml` starts these services:

- `mysql`: Slurm accounting database
- `slurmdbd`: Slurm database daemon
- `slurmctld`: Slurm controller
- `slurmrestd`: Slurm REST daemon
- `c1` through `c8`: compute nodes running `slurmd`

By default, this gives you an eight-node Slurm cluster.

Each Slurm service runs with Docker `init: true` so exited child processes are
reaped correctly inside the containers.

## Repository Files That Feed The Containers

The image build copies these repository files into `/etc/slurm`:

- `slurm.conf`
- `slurmdbd.conf`
- `gres.conf`
- `rest.conf`
- `cgroup.conf`

Those copies happen in [Dockerfile](Dockerfile) during `docker build`.

There is an important runtime detail:

- the compose stack mounts the named volume `etc_slurm` on `/etc/slurm`
- once that volume exists, it overrides the image-baked `/etc/slurm` files

That means:

- changing `slurm.conf` in this repository updates the repository source
- rebuilding the image updates the image contents
- but an existing running cluster still uses the persistent `etc_slurm` volume until you refresh or recreate it

This is why the repo copy of `slurm.conf` can differ from the file you see inside `slurmctld`.

## Host Workspace Layout

The cluster bind-mounts the host workspace configured in `qfw-install.env`
through `QFW_CONTAINER_BASE` into the containers at:

```text
/workspace/qfw-container-base
```

By default, `./do_configure.sh` creates:

```text
../qfw-container-base
```

The intended host layout under that directory is:

```text
qfw-container-base/
  QFw/          # active source checkout
  venv/         # container-created persistent Python venv
  build/        # persistent build tree
  install/      # persistent install tree
  rocm/         # optional mounted ROCm tree for module load rocm
```

This mount is present in all Slurm service containers:

- `slurmdbd`
- `slurmctld`
- `slurmrestd`
- `c1` through `c8`

That means you can edit QFw on the host and immediately see the changes inside
the containers without rebuilding the image.

The mounted QFw checkout is optional for users who only want to run the
image-contained QFw. It is still the normal development path. If the mounted
checkout builds its own circuit runners, its `qfw_activate` prepends its paths
and those runners win. If it does not, the prebuilt image runners remain
available from `/opt/qfw/qhpc/QFw/bin`.

## Prerequisites

You need:

- Docker
- Docker Compose

All commands below assume you are in:

```bash
cd QFw-SLURM-Cluster
```

## Quick Start

If you want the shortest exact sequence to install, build, and run:

```bash
cd QFw-SLURM-Cluster
./do_configure.sh
./do_build.sh
./do_startup.sh
./do_ssh.sh
```

Inside `slurmctld`, verify the cluster:

```bash
sinfo
scontrol show nodes
```

## Prepare The Host Workspace

Before building or starting the containers, create the host-mounted workspace
layout and write the install settings file:

```bash
./do_configure.sh
```

That script creates the configured `QFW_CONTAINER_BASE` directory and the
persistent directories the containers expect:

- `QFw/`
- `venv/`
- `build/`
- `install/`
- `benchmarks/`
- `rocm/`

It also checks whether `QFW_CONTAINER_BASE/QFw` already contains a QFw
checkout. The venv is not created here because it should be created later from
inside the container so it matches the container Python version.

## Build The Image With The Helper

To build the configured image without typing the raw `docker build` command:

```bash
./do_build.sh
```

If `qfw-install.env` does not exist yet, this helper runs `./do_configure.sh`
with its default settings first and then builds the image.

The image-contained QFw build uses `QFW_BUILD_JOBS=4` by default. The helper
writes this value to `qfw-install.env` and passes it to `docker build`.

Set a different value during configuration if your host needs more or fewer
parallel build jobs:

```bash
./do_configure.sh --qfw-build-jobs 2
./do_build.sh
```

If you want a clean rebuild from scratch and want the current compose stack
removed first:

```bash
./do_build.sh --force
```

This stops and removes the current compose stack through `./do_stop.sh delete`
and then runs `docker build --no-cache`. It does not automatically start the
cluster again.

If containers already exist for the same image tag after a rebuild, recreate
them so Docker does not keep using the old containers:

```bash
./do_restart.sh --force-recreate
```

## Docker For Beginners

This section uses this Slurm cluster as the example and focuses on the Docker
commands you are most likely to need day to day.

### Build the image

This turns the `Dockerfile` into a reusable local image using the values from
`qfw-install.env`:

```bash
./do_configure.sh
./do_build.sh
```

Think of this as "compile the container image from the recipe in this
directory."

### Rebuild from scratch

This ignores Docker cache and rebuilds every layer:

```bash
./do_configure.sh
./do_build.sh --force
```

Use this when:

- you suspect stale Docker cache
- you changed an early image layer
- you want a clean validation build

### Start the cluster

This creates and starts all services from `docker-compose.yml` using the values
from `qfw-install.env`:

```bash
docker compose --env-file qfw-install.env up -d
```

Use `-d` for detached mode so the cluster keeps running in the background.

### Start and register the cluster with the helper

This is the easiest way to bring the cluster up for normal use:

```bash
./do_startup.sh
```

It:

1. starts the compose services
2. waits for `slurmdbd`
3. registers the Slurm cluster

### Show what is running

See which containers are up:

```bash
docker compose --env-file qfw-install.env ps
```

See local images:

```bash
docker images
```

### View logs

Follow all compose service logs:

```bash
docker compose --env-file qfw-install.env logs -f
```

View logs for one service:

```bash
docker compose --env-file qfw-install.env logs -f slurmctld
docker compose --env-file qfw-install.env logs -f c5
```

### Enter a running container

Open an interactive shell inside a container:

```bash
./do_ssh.sh
./do_ssh.sh c1
```

Use this when you want to run `sinfo`, `salloc`, `module load`, or inspect files
inside the container.

### Stop the cluster

Stop running containers without deleting them:

```bash
docker compose --env-file qfw-install.env stop
```

Bring them back later:

```bash
docker compose --env-file qfw-install.env start
```

### Restart the cluster

Restart all compose services:

```bash
docker compose --env-file qfw-install.env restart
```

This is useful after config refreshes.

Use the helper when you want the same behavior:

```bash
./do_restart.sh
```

If you rebuilt the image and need existing containers recreated from the new
image, use:

```bash
./do_restart.sh --force-recreate
```

That runs:

```bash
docker compose --env-file qfw-install.env up -d --force-recreate
```

### Remove the cluster but keep images

Remove the running containers and network, but keep named volumes unless you add
`-v`:

```bash
docker compose --env-file qfw-install.env down
```

### Factory reset the cluster

Remove containers and named volumes:

```bash
docker compose --env-file qfw-install.env down -v
```

This is the closest thing to a factory reset for this setup. It wipes the
persistent Slurm volumes, including the live `/etc/slurm` volume.

After that, recreate the cluster from the current repo and image:

```bash
./do_startup.sh
```

### Refresh repo config into running containers

If you changed `slurm.conf`, `gres.conf`, or related Slurm config files and do
not want to rebuild the image:

```bash
./update_slurmfiles.sh slurm.conf
./update_slurmfiles.sh slurm.conf gres.conf
```

This copies the selected repo files into `/etc/slurm` inside the running
cluster and restarts the services.

### Remove a local image

If you want to delete a built image from your machine:

```bash
docker rmi ${IMAGE_NAME}:${IMAGE_TAG}
```

Do this only when you really want to free space or force a rebuild path.

### Mental model

The common workflow is:

1. `./do_build.sh`
2. `docker compose --env-file qfw-install.env up -d` or `./do_startup.sh`
3. `./do_ssh.sh`
4. work inside the running cluster
5. `./update_slurmfiles.sh ...` for config-only changes
6. `docker compose --env-file qfw-install.env down -v` when you want to fully reset the cluster state

## Image Build Notes

For the practical build, start, stop, reset, and log commands, use the
`Docker For Beginners` section above.

One additional image-specific note is useful here:

If you want shell commands like `docker build -t ${IMAGE_NAME}:${IMAGE_TAG}` to
use the same values as the helper scripts, export `qfw-install.env` into your shell first:

```bash
set -a
source qfw-install.env
set +a
```

### Compose-driven build

If you prefer using compose and `qfw-install.env` instead of an explicit
`docker build` command:

```bash
docker compose --env-file qfw-install.env build
```

Compose uses:

- `SLURM_TAG` for the Slurm source tag
- `QFW_BUILD_JOBS` for the image-contained QFw build parallelism
- `IMAGE_NAME` for the runtime image repository name
- `IMAGE_TAG` for the runtime image tag

If you want compose to use the image built by hand, keep both `IMAGE_NAME` and
`IMAGE_TAG` aligned with the image you built.

## Accessing the Cluster Interactively

Open a shell in the Slurm controller:

```bash
./do_ssh.sh
```

Open a shell in a compute node:

```bash
./do_ssh.sh c1
./do_ssh.sh c2
```

Once inside `slurmctld`, basic Slurm inspection looks like:

```bash
sinfo
scontrol show nodes
squeue
```

Expected `sinfo` shape:

```text
PARTITION AVAIL  TIMELIMIT  NODES  STATE NODELIST
normal*      up 5-00:00:00      4   idle c[1-4]
quantum      up   infinite      4   idle c[5-8]
```

## Using the Module Utility

The image includes `environment-modules`. The modulefiles live in:

```text
/etc/modulefiles
```

Typical usage:

```bash
module use /etc/modulefiles
module avail
module load gcc-native/13.2
module load cmake
module load openblas
module load swig
```

Compatibility alias:

```bash
module load gcc/13.2
```

ROCm is treated as a mounted prefix. By default the modulefile expects:

```text
/workspace/qfw-container-base/rocm
```

or you can override it:

```bash
export QFW_ROCM_ROOT=/workspace/qfw-container-base/rocm
module use /etc/modulefiles
module load rocm
```

## Persistent Python Virtual Environment

The recommended model is:

- create the venv inside the container
- store it on the mounted host path
- recreate it whenever you switch the container Python version

Example from inside `slurmctld`:

```bash
rm -rf /workspace/qfw-container-base/venv
python3 -m venv /workspace/qfw-container-base/venv
source /workspace/qfw-container-base/venv/bin/activate
python --version
```

Because the venv directory is on the host mount, it survives container removal.
That also means an older venv can outlive an image rebuild. If you rebuild the
image with a different Python version, remove and recreate the mounted venv so
it matches the current container interpreter.

## QFw Source Workflow

The image already includes a runnable QFw install at:

```text
/opt/qfw/qhpc/QFw
```

For a quick image-contained QFw shell:

```bash
cd /opt/qfw/qhpc/QFw
source /opt/qfw/qhpc/QFw/setup/qfw_activate
```

The active QFw checkout should live at:

```text
/workspace/qfw-container-base/QFw
```

Typical interactive flow inside `slurmctld`:

```bash
cd /workspace/qfw-container-base/QFw
source /workspace/qfw-container-base/venv/bin/activate
module use /etc/modulefiles
module load gcc-native/13.2 cmake openblas swig
```

Then build or run QFw directly from the mounted source tree.

Any file edited on the host is visible immediately in the container.

The mounted development checkout can reuse the image-built circuit runners
without rebuilding TNQVM or NWQ-Sim. The image exposes the required binary and
library paths globally:

```text
/opt/qfw/openmpi/bin
/opt/qfw/libfabric/bin
/opt/qfw/qhpc/QFw/bin
/opt/qfw/openmpi/lib
/opt/qfw/libfabric/lib
/opt/qfw/qhpc/install/image/TNQVM/exatn/lib
/opt/qfw/qhpc/install/image/TNQVM/xacc/lib
/opt/qfw/qhpc/build/image/TNQVM/tnqvm/plugins
/opt/qfw/qhpc/install/image/NWQSIM/lib
```

If the mounted checkout is configured with its own build paths, QFw prepends
those paths during activation, so development artifacts take precedence over
the image artifacts.

## Shared Job Directories

Two shared locations matter:

- `/data`
  - backed by the named `slurm_jobdir` volume
  - good for Slurm job outputs and cluster-visible files
- `/mnt`
  - backed by `./shared-dir`
  - good for host-managed scripts you want visible in containers

## Submitting Jobs

### Simple `sbatch`

From `slurmctld`:

```bash
cd /data
sbatch --wrap="hostname"
```

Inspect output:

```bash
cat /data/slurm-<jobid>.out
```

### Use a script from the host-mounted shared directory

Example:

```bash
sbatch /mnt/simple.sbatch
```

### Run a command immediately with `srun`

```bash
srun -N1 -n1 hostname
```

### Allocate nodes interactively with `salloc`

Request one node:

```bash
salloc -N1 -n1
```

Request both nodes:

```bash
salloc -N2 -n2
```

Then launch commands inside the allocation:

```bash
srun hostname
srun -N2 -n2 hostname
```

Inspect the allocation:

```bash
squeue
scontrol show job <jobid>
```

## Running Across Multiple Nodes

This cluster starts with eight compute nodes: `c1` through `c8`.

Example:

```bash
srun -N2 -n2 hostname
```

You should see one rank land on each node.

For MPI-style tests from inside the cluster:

```bash
export PATH=/opt/qfw/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/opt/qfw/openmpi/lib:/opt/qfw/libfabric/lib:$LD_LIBRARY_PATH

srun -N2 -n2 /opt/qfw/osu-micro-benchmarks/libexec/osu-micro-benchmarks/mpi/pt2pt/osu_latency
```

For plain `mpirun` tests:

```bash
export PATH=/opt/qfw/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/opt/qfw/openmpi/lib:/opt/qfw/libfabric/lib:$LD_LIBRARY_PATH
export OMPI_ALLOW_RUN_AS_ROOT=1
export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1

mpirun -np 2 /opt/qfw/osu-micro-benchmarks/libexec/osu-micro-benchmarks/mpi/pt2pt/osu_latency
```

Use `srun` when you want Slurm to control placement. Use `mpirun` for direct MPI
sanity checks inside a container shell.

## Adding More Nodes

Adding nodes requires updating both the compose topology and the Slurm config.

### 1. Add a new service in `docker-compose.yml`

Use any of the existing `c1` through `c8` services as a template and add `c9`,
`c10`, and so on.

Each new node should:

- use the same image
- run `command: ["slurmd"]`
- join `slurm-network`
- mount the same Slurm, log, `/data`, and QFw workspace volumes

### 2. Update `slurm.conf`

Add the new node definition and update the partition:

```text
NodeName=c3 CPUs=...
PartitionName=normal Nodes=c[1-3] Default=YES MaxTime=5-00:00:00 State=UP
```

### 3. Push the updated config into the running cluster

```bash
./update_slurmfiles.sh slurm.conf
docker compose --env-file qfw-install.env restart
```

If the cluster metadata also needs to be refreshed, rerun:

```bash
./register_cluster.sh
```

## Updating Slurm Configuration Without Rebuilding

You can change these repository files without rebuilding the image:

- `slurm.conf`
- `slurmdbd.conf`
- `gres.conf`
- `rest.conf`
- `cgroup.conf`

To push updated repo copies into the running cluster, use:

```bash
./update_slurmfiles.sh slurm.conf
```

You can pass more than one file:

```bash
./update_slurmfiles.sh slurm.conf gres.conf rest.conf
```

`update_slurmfiles.sh` does two things:

1. copies the selected repo files into `/etc/slurm` inside `slurmctld`
2. runs `docker compose --env-file qfw-install.env restart`

That is the normal way to refresh config in a running cluster without rebuilding
the image.

### Verifying the live config

Check the file inside the running controller:

```bash
docker exec -it slurmctld bash -lc 'cat /etc/slurm/slurm.conf'
```

Check the live scheduler view:

```bash
docker exec -it slurmctld bash -lc 'sinfo'
docker exec -it slurmctld bash -lc 'scontrol show partition'
docker exec -it slurmctld bash -lc 'scontrol show nodes'
```

### When a rebuild is actually needed

Rebuild the image only when you change something that is part of the image
itself, for example:

- `Dockerfile`
- installed packages
- source-built dependencies like `libfabric` or OpenMPI
- modulefiles under `modulefiles/`

For plain Slurm config changes, use `./update_slurmfiles.sh ...` instead of
rebuilding.

## REST API

`slurmrestd` is exposed on:

```text
http://localhost:6820
```

The `rest-testing/` directory contains example scripts and client code for
interacting with the REST API.

## Notes and Caveats

- This is a Docker-based virtual cluster, not a hardware-faithful HPC system.
- It is useful for framework debugging, integration testing, and profiling
  software overhead.
- It will not reproduce real production interconnect behavior.
- The image patches Slurm's completion profile script so it exits early in
  non-interactive shells. This keeps SSH-launched QFw commands from failing
  before PRTE startup while preserving completion for interactive shells.
- The compose stack shares `/root/.ssh` across Slurm containers and starts
  `sshd`, so root-to-root SSH between containers works for QFw launch paths.

## Typical End-to-End Session

Build:

```bash
./do_build.sh
```

Start and register:

```bash
./do_startup.sh
```

Enter the controller:

```bash
./do_ssh.sh
```

Prepare environment:

```bash
module use /etc/modulefiles
module load gcc-native/13.2 cmake openblas swig
source /workspace/qfw-container-base/venv/bin/activate
cd /workspace/qfw-container-base/QFw
```

Inspect cluster:

```bash
sinfo
squeue
```

Allocate two nodes:

```bash
salloc -N2 -n2
```

Run a multi-node command:

```bash
srun -N2 -n2 hostname
```
