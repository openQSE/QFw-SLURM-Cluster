# QFw Slurm Docker Cluster

This directory contains a Docker-based Slurm cluster that has been extended to
serve as a QFw and DEFw development and profiling environment.

The intent is to keep the heavy runtime stack inside the image and keep the
active QFw workspace on the host. That gives you:

- a repeatable Slurm test cluster
- a repeatable MPI/libfabric toolchain
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

## Cluster Topology

`docker-compose.yml` starts these services:

- `mysql`: Slurm accounting database
- `slurmdbd`: Slurm database daemon
- `slurmctld`: Slurm controller
- `slurmrestd`: Slurm REST daemon
- `c1` through `c8`: compute nodes running `slurmd`

By default, this gives you an eight-node Slurm cluster.

## Repository Files That Feed The Containers

The image build copies these repository files into `/etc/slurm`:

- `slurm.conf`
- `slurmdbd.conf`
- `gres.conf`
- `rest.conf`
- `cgroup.conf`

Those copies happen in [Dockerfile](/home/a2e/ORNL/Quantum/openQSE/slurm-docker-cluster/Dockerfile) during `docker build`.

There is an important runtime detail:

- the compose stack mounts the named volume `etc_slurm` on `/etc/slurm`
- once that volume exists, it overrides the image-baked `/etc/slurm` files

That means:

- changing `slurm-docker-cluster/slurm.conf` updates the repository source
- rebuilding the image updates the image contents
- but an existing running cluster still uses the persistent `etc_slurm` volume until you refresh or recreate it

This is why the repo copy of `slurm.conf` can differ from the file you see inside `slurmctld`.

## Host Workspace Layout

The cluster bind-mounts `../qfw-container-base` into the containers at:

```text
/workspace/qfw-container-base
```

The intended host layout is:

```text
qfw-container-base/
  QFw/          # active source checkout
  venv/         # container-created persistent Python venv
  build/        # persistent build tree
  install/      # persistent install tree
  rocm/         # optional mounted ROCm tree for module load rocm
```

This mount is present in:

- `slurmdbd`
- `slurmctld`
- `slurmrestd`
- `c1`
- `c2`

That means you can edit QFw on the host and immediately see the changes inside
the containers without rebuilding the image.

## Prerequisites

You need:

- Docker
- Docker Compose

All commands below assume you are in:

```bash
cd slurm-docker-cluster
```

## Docker For Beginners

This section uses this Slurm cluster as the example and focuses on the Docker
commands you are most likely to need day to day.

### Build the image

This turns the `Dockerfile` into a reusable local image:

```bash
docker build -t slurm-docker-cluster:25.05.0 --build-arg SLURM_TAG=slurm-25-05-2-1 .
```

Think of this as "compile the container image from the recipe in this
directory."

### Rebuild from scratch

This ignores Docker cache and rebuilds every layer:

```bash
docker build --no-cache -t slurm-docker-cluster:qfw-full --build-arg SLURM_TAG=slurm-25-05-2-1 .
```

Use this when:

- you suspect stale Docker cache
- you changed an early image layer
- you want a clean validation build

### Start the cluster

This creates and starts all services from `docker-compose.yml`:

```bash
docker compose up -d
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
docker compose ps
```

See local images:

```bash
docker images
```

### View logs

Follow all compose service logs:

```bash
docker compose logs -f
```

View logs for one service:

```bash
docker compose logs -f slurmctld
docker compose logs -f c5
```

### Enter a running container

Open an interactive shell inside a container:

```bash
docker exec -it slurmctld bash
docker exec -it c1 bash
```

Use this when you want to run `sinfo`, `salloc`, `module load`, or inspect files
inside the container.

### Stop the cluster

Stop running containers without deleting them:

```bash
docker compose stop
```

Bring them back later:

```bash
docker compose start
```

### Restart the cluster

Restart all compose services:

```bash
docker compose restart
```

This is useful after config refreshes.

### Remove the cluster but keep images

Remove the running containers and network, but keep named volumes unless you add
`-v`:

```bash
docker compose down
```

### Factory reset the cluster

Remove containers and named volumes:

```bash
docker compose down -v
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
docker rmi slurm-docker-cluster:25.05.0
```

Do this only when you really want to free space or force a rebuild path.

### Mental model

The common workflow is:

1. `docker build ...`
2. `docker compose up -d` or `./do_startup.sh`
3. `docker exec -it slurmctld bash`
4. work inside the running cluster
5. `./update_slurmfiles.sh ...` for config-only changes
6. `docker compose down -v` when you want to fully reset the cluster state

## Image Build Notes

For the practical build, start, stop, reset, and log commands, use the
`Docker For Beginners` section above.

One additional image-specific note is useful here:

### Compose-driven build

If you prefer using compose and the `.env` file instead of an explicit
`docker build` command:

```bash
docker compose build
```

Compose uses:

- `SLURM_TAG` for the Slurm source tag
- `IMAGE_TAG` for the runtime image tag

If you want compose to use the image built by hand, keep the tag aligned with
`IMAGE_TAG`.

## Accessing the Cluster Interactively

Open a shell in the Slurm controller:

```bash
docker exec -it slurmctld bash
```

Open a shell in a compute node:

```bash
docker exec -it c1 bash
docker exec -it c2 bash
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
normal*      up 5-00:00:00      2   idle c[1-2]
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

This cluster starts with `c1` and `c2`, so multi-node tests are straightforward.

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

Use `c1` or `c2` as a template and add `c3`, `c4`, and so on.

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
docker compose restart
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
2. runs `docker compose restart`

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
- The shell currently prints a `slurm_completion.sh` startup warning in some
  `bash -lc` paths. It does not block cluster operation or module loading.

## Typical End-to-End Session

Build:

```bash
docker build -t slurm-docker-cluster:25.05.0 --build-arg SLURM_TAG=slurm-25-05-2-1 .
```

Start and register:

```bash
./do_startup.sh
```

Enter the controller:

```bash
docker exec -it slurmctld bash
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
