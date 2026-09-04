# [QFw]-SLURM Environment

[QFw]-SLURM Environment is a Docker Compose based [Slurm] cluster for [QFw]
development, integration testing, and profiling. It packages the heavy runtime
stack in the image, while keeping the active [QFw] development tree on a host
mount.

[QFw] itself is not baked into the image. You clone it onto the host mount and
build it inside the running cluster with `./do_qfw_build.sh`, so every node sees
the same install and the tree being built is your own checkout.

This is not meant to model production HPC performance. It is meant to give a
repeatable [Slurm], MPI, [libfabric], [DEFw], and [QFw] test environment.

The image also includes the lower-level interface libraries that the [QFw]
QPU front-end shim routes to: [QRMI] (Rust library, Python bindings, and the
SLURM SPANK plugin) and [QDMI] (via IQM's `iqm-qdmi` reference implementation).

## Table Of Contents

- [Build The Environment](#build-the-environment)
- [Start And Use The Cluster](#start-and-use-the-cluster)
- [Build And Run QFw](#build-and-run-qfw)
- [Running Against The IQM QPU](IQM-ACCESS.md) — credentials, remote access, hardware smoke tests
- [Design Overview](#design-overview)
- [Detailed Reference](#detailed-reference)
- [Troubleshooting](#troubleshooting)

## Build The Environment

<details open>
<summary>Build a local image or configure a pulled image</summary>

All commands assume you are in this repository:

```bash
cd QFw-SLURM-Cluster
```

Required host tools:

- Docker
- Docker Compose

Build the image locally with the default settings:

```bash
./do_configure.sh
./do_build.sh
```

If `--prefix` is omitted, `do_configure.sh` creates and uses:

```text
./shared-dir
```

Build with an explicit host mount and image name:

```bash
./do_configure.sh \
  --prefix /path/to/shared-dir \
  --image-name qfw-slurm-cluster \
  --image-tag rocky10.1 \
  --qfw-build-jobs 4

./do_build.sh
```

Build and tag an image for GHCR:

```bash
./do_configure.sh \
  --prefix /path/to/shared-dir \
  --image ghcr.io/openqse/qfw-slurm-cluster:20260503-v1.0 \
  --qfw-build-jobs 4

./do_build.sh
```

Use an already-built image without rebuilding:

```bash
docker pull ghcr.io/openqse/qfw-slurm-cluster:20260503-v1.0

./do_configure.sh \
  --prefix /path/to/shared-dir \
  --image ghcr.io/openqse/qfw-slurm-cluster:20260503-v1.0

./do_startup.sh
```

Do not run `./do_build.sh` in the prebuilt-image workflow unless you intend to
rebuild the image locally.

For a private GHCR image, log in first with a GitHub token that has
`read:packages` access:

```bash
echo "${GHCR_TOKEN}" | docker login ghcr.io \
  -u <github-username> \
  --password-stdin
```

</details>

## Start And Use The Cluster

<details open>
<summary>Start, enter, inspect, and stop the [Slurm] cluster</summary>

Start the cluster and register it with [Slurm]DBD:

```bash
./do_startup.sh
```

Enter the [Slurm] controller:

```bash
./do_ssh.sh
```

Enter a compute node:

```bash
./do_ssh.sh c1
./do_ssh.sh c2
```

Inspect [Slurm] from inside `slurmctld`:

```bash
sinfo
scontrol show nodes
squeue
```

Run a simple [Slurm] command:

```bash
srun -N1 -n1 hostname
```

Allocate two nodes interactively:

```bash
salloc -N2 -n2
srun hostname
```

Stop the cluster without deleting named volumes:

```bash
./do_stop.sh
```

Stop and remove containers plus named volumes:

```bash
./do_stop.sh delete
```

If you rebuild an image and need existing containers recreated from the new
image:

```bash
./do_restart.sh --force-recreate
```

</details>

To validate the QRMI/QDMI shim (a smoke test — local routing/normalization, and device introspection on IQM hardware), see [TESTING.md](TESTING.md).

## Build And Run [QFw]

<details open>
<summary>Clone, build, and run [QFw]</summary>

[QFw] is not part of the image. `do_configure.sh` writes `QFW_CONTAINER_BASE`
into `qfw-install.env` and `.env`, and Docker Compose bind-mounts that host
directory into every [Slurm] container at:

```text
/workspace/qfw-container-base
```

`do_qfw_build.sh` builds [QFw] inside the running cluster and writes everything
to that shared mount, so every node sees the same install:

```text
shared-dir/
  QFw/            # your QFw checkout, cloned in step 1
  qfw-venv/       # Python venv, created by do_qfw_build.sh
  qfw-build/      # CMake build tree
  qfw-install/    # install tree
```

1. Configure the host mount and clone [QFw]:

```bash
./do_configure.sh

git clone --recursive https://github.com/openQSE/QFw.git shared-dir/QFw
```

`do_configure.sh` defaults to `./shared-dir`. Pass `--prefix` to put the mount
somewhere else, and clone into that directory instead.

`--recursive` is required. [QFw] carries [DEFw] and the `qhw-*` packages as
submodules and the build needs all of them. [QFw] declares those submodules over
SSH, so without GitHub SSH access, rewrite them to HTTPS first:

```bash
git config --global url."https://github.com/".insteadOf "git@github.com:"
```

2. Start the cluster:

```bash
./do_startup.sh
```

3. Build [QFw] and [DEFw] inside `slurmctld`:

```bash
./do_qfw_build.sh
```

This creates the venv, installs [QFw]'s requirements along with the [QRMI] and
[QDMI] Python bindings, then runs the CMake configure, build, and install. Use
`--clean` to discard the build and install trees first, `--skip-venv` to reuse
the existing venv, and `--jobs N` to set parallelism.

4. Activate [QFw] inside a container:

```bash
./do_ssh.sh

source /workspace/qfw-container-base/qfw-install/bin/qfw-activate \
  --venv /workspace/qfw-container-base/qfw-venv
```

5. Run the [QFw] MPI smoke test:

```bash
cd /workspace/qfw-container-base/QFw/examples
./qfw_mpi_smoke.sh
```

`./qfw_shim_smoke.sh` in the same directory exercises the QRMI/QDMI shim.
See [TESTING.md](TESTING.md) for running it against real IQM hardware.

**The simulator examples do not currently run.** The CMake build no longer
produces the [TNQVM] and [NWQ-Sim] executables that the older `qfw_build.sh`
built, and nothing provisions them in the image, so `qfw_ghz.sh`, `qfw_qaoa.sh`,
`qfw_supermarq.sh` and `qfw_run_all.sh` fail whichever backend you pass. This is
tracked in [openQSE/QFw#58](https://github.com/openQSE/QFw/issues/58). The
hardware path is unaffected, because the [QRMI]/[QDMI] shim does not use those
backends.

</details>

## Design Overview

<details>
<summary>High-level architecture</summary>

The environment has three important layers:

- Host workspace: scripts, plus the QFw checkout and its venv, build, and install trees.
- Docker image: [Slurm], [OpenMPI], [libfabric], modules, and the [QRMI] runtime.
- Compose cluster: [Slurm] services and compute nodes using the image and mount.

```mermaid
flowchart TB
    host["Host workspace\nQFW_CONTAINER_BASE"] -->|bind mount| mount["/workspace/qfw-container-base\nQFw checkout, venv, build, install"]

    subgraph img["Docker image"]
        slurm["Slurm runtime"]
        mpi["libfabric + OpenMPI/PRRTE"]
        qrmi["/opt/qfw/qrmi\nQRMI C library + SPANK plugin"]
    end

    subgraph cluster["Docker Compose cluster"]
        mysql["mysql"]
        dbd["slurmdbd"]
        ctl["slurmctld"]
        rest["slurmrestd\nlocalhost:6820"]
        subgraph nodes["compute nodes"]
            c1["c1..c4\nnormal partition"]
            c5["c5..c8\nquantum partition"]
        end
    end

    mount --> ctl
    mount --> c1
    mount --> c5
    qrmi --> ctl
    qrmi --> c1
    qrmi --> c5
    mysql --> dbd
    dbd --> ctl
    ctl --> c1
    ctl --> c5
    ctl --> rest
```

[QFw] runtime tests commonly use a heterogeneous [Slurm] allocation. The
application runs on group 0, while resource-manager and QPM services run on
group 1. QPM services may launch simulators through MPI/PRTE or talk directly
to a device or service backend.

QPM service examples include [TNQVM] and [NWQ-Sim].

```mermaid
flowchart LR
    subgraph g0["Slurm het-group 0"]
        app["QFw application\nQiskit/PennyLane/test script"]
    end

    subgraph g1["Slurm het-group 1"]
        resmgr["QFw resource manager"]
        qpm["QPM service\nTNQVM, NWQ-Sim, IQM, etc."]
        dvm["PRTE DVM\noptional MPI launch layer"]
        target["Simulator or hardware backend"]
    end

    app --> resmgr
    resmgr --> qpm
    qpm --> dvm
    dvm --> target
    qpm -.-> target
```

</details>

## Detailed Reference

<details>
<summary>What the image contains</summary>

The image builds and installs:

- [Slurm]
- Rocky 10 system Python 3.12
- `environment-modules`
- GCC toolchain from Rocky 10
- [libfabric]
- [OpenMPI] with the bundled [PRRTE] checkout
- OSU Micro-Benchmarks
- [QFw] build dependencies such as `cmake`, `gcc-gfortran`, `openblas-devel`,
  `swig`, `scons`, `ninja-build`, and a pinned Rust toolchain under
  `/opt/qfw/rust`
- [QRMI] runtime: `libqrmi.so` and `qrmi.h` under `/opt/qfw/qrmi/`, and the
  SLURM SPANK plugin installed into `/usr/lib64/slurm/`

[QFw] itself is not in the image, and neither are the [QRMI] and [QDMI] Python
bindings. `do_qfw_build.sh` installs those into the shared-mount venv, pinned to
the `QRMI_VERSION` the image exports so the bindings match the C ABI it ships.

The image-level runtime environment includes:

```text
/opt/qfw/openmpi/bin
/opt/qfw/libfabric/bin
/opt/qfw/rust/cargo/bin
/opt/qfw/openmpi/lib
/opt/qfw/libfabric/lib
/opt/qfw/qrmi/lib
```

`QRMI_PREFIX` is set to `/opt/qfw/qrmi` so consumers can locate the QRMI
headers and shared library without hard-coding the path.

`qfw-activate` is explicit. The image entrypoint does not globally source it
because activation rewires the Python environment.

</details>

<details>
<summary>Helper scripts and generated files</summary>

`./do_configure.sh` prepares the host workspace and writes:

- `qfw-install.env`, used by helper scripts
- `.env`, used by Docker Compose

Useful options:

```bash
./do_configure.sh --help
./do_configure.sh --dry-run
./do_configure.sh --prefix /path/to/shared-dir
./do_configure.sh --image ghcr.io/openqse/qfw-slurm-cluster:20260503-v1.0
./do_configure.sh --qfw-build-jobs 4
```

`./do_build.sh` builds the configured image:

```bash
./do_build.sh
./do_build.sh --dry-run
./do_build.sh --force
```

`--force` stops and removes the current Compose stack with
`./do_stop.sh delete` and rebuilds with `docker build --no-cache`.

`./do_startup.sh` starts the Compose services, waits for `slurmdbd`, and runs
`./register_cluster.sh`.

`./do_images.sh` lists local image variants:

```bash
./do_images.sh
./do_images.sh --configured
./do_images.sh --configured --history
./do_images.sh --repo ghcr.io/openqse/qfw-slurm-cluster --tag 20260503-v1.0
```

</details>

<details>
<summary>Cluster topology</summary>

`docker-compose.yml` starts:

- `mysql`: [Slurm] accounting database
- `slurmdbd`: [Slurm] database daemon
- `slurmctld`: [Slurm] controller
- `slurmrestd`: [Slurm] REST daemon, exposed on `localhost:6820`
- `c1` through `c8`: compute nodes running `slurmd`

The current [Slurm] config defines:

- `normal`: `c1` through `c4`
- `quantum`: `c5` through `c8`

The quantum nodes carry example `Gres` and `Features` values for QPU-oriented
testing.

Each [Slurm] service runs with Docker `init: true` so exited child processes are
reaped correctly inside containers.

</details>

<details>
<summary>Persistent mounts and volumes</summary>

The host [QFw] workspace is mounted into all [Slurm] service containers:

```text
${QFW_CONTAINER_BASE}:/workspace/qfw-container-base
```

Other important shared paths are:

- `/data`: backed by the `slurm_jobdir` named volume, useful for [Slurm] job
  outputs.
- `/mnt`: backed by `./shared-dir`, useful for host-managed scripts visible in
  the containers.
- `/etc/slurm`: backed by the `etc_slurm` named volume after the cluster is
  created.

The `/etc/slurm` volume is important. The Docker image copies repository [Slurm]
configuration into `/etc/slurm` during build, but once the named volume exists,
the volume overrides the image-baked files. Use `./update_slurmfiles.sh` to
refresh live [Slurm] config without rebuilding:

```bash
./update_slurmfiles.sh slurm.conf
./update_slurmfiles.sh slurm.conf gres.conf rest.conf
```

If you change the configured host mount path after containers already exist,
recreate the containers:

```bash
./do_restart.sh --force-recreate
```

For a full reset, including named volumes:

```bash
./do_stop.sh delete
./do_startup.sh
```

</details>

<details>
<summary>Modules, ROCm, and MPI checks</summary>

The image includes `environment-modules` and modulefiles in:

```text
/etc/modulefiles
```

Typical interactive use:

```bash
module use /etc/modulefiles
module avail
module load gcc-native/13.2 cmake openblas swig
```

ROCm can be provided as an optional mounted prefix. If you need it, create and
use:

```text
/workspace/qfw-container-base/rocm
```

Override it if needed:

```bash
export QFW_ROCM_ROOT=/workspace/qfw-container-base/rocm
module use /etc/modulefiles
module load rocm
```

Run an MPI sanity check through [Slurm]:

```bash
srun -N2 -n2 \
  /opt/qfw/osu-micro-benchmarks/libexec/osu-micro-benchmarks/mpi/pt2pt/osu_latency
```

Run a direct `mpirun` sanity check:

```bash
export OMPI_ALLOW_RUN_AS_ROOT=1
export OMPI_ALLOW_RUN_AS_ROOT_CONFIRM=1

mpirun -np 2 \
  /opt/qfw/osu-micro-benchmarks/libexec/osu-micro-benchmarks/mpi/pt2pt/osu_latency
```

Use `srun` when [Slurm] should control placement. Use `mpirun` for direct MPI
sanity checks inside a container shell.

</details>

<details>
<summary>Submitting jobs and using REST</summary>

Submit a simple batch job from inside `slurmctld`:

```bash
cd /data
sbatch --wrap="hostname"
cat /data/slurm-<jobid>.out
```

Submit a script from the host-managed shared directory:

```bash
sbatch /mnt/simple.sbatch
```

Run commands immediately:

```bash
srun -N1 -n1 hostname
srun -N2 -n2 hostname
```

The [Slurm] REST daemon is exposed on:

```text
http://localhost:6820
```

The `rest-testing/` directory contains example REST scripts and client code.

</details>

<details>
<summary>Image names, GHCR, and local image inspection</summary>

Docker image repository names must be lowercase and may contain path components
separated by `/`, using letters, digits, `.`, `_`, and `-`.

Good examples:

```text
qfw-slurm-cluster:rocky10.1
ghcr.io/openqse/qfw-slurm-cluster:20260503-v1.0
```

Inspect the configured local image:

```bash
./do_images.sh --configured
```

Inspect image layer sizes before pushing to GHCR:

```bash
./do_images.sh --configured --history
```

GHCR allows up to 10 GB per layer and has an upload timeout. A total image can
be larger than 10 GB if each individual layer is below the layer limit.

</details>

<details>
<summary>Adding nodes or changing [Slurm] config</summary>

To add more compute nodes:

1. Add a new service to `docker-compose.yml` using `c1` through `c8` as a
   template.
2. Add the node to `slurm.conf`.
3. Refresh the live cluster config.

Example refresh:

```bash
./update_slurmfiles.sh slurm.conf
docker compose --env-file qfw-install.env restart
./register_cluster.sh
```

Rebuild the image only when you change image contents, such as:

- `Dockerfile`
- installed packages
- source-built dependencies such as [libfabric] or [OpenMPI]
- modulefiles under `modulefiles/`

For plain [Slurm] config changes, use `./update_slurmfiles.sh ...`.

</details>

<details>
<summary>Notes and caveats</summary>

- This is a Docker-based virtual [Slurm] cluster, not a hardware-faithful HPC
  system.
- It is useful for [QFw] integration testing, launcher debugging, service
  bring-up, and software-overhead profiling.
- It will not reproduce production interconnect behavior.
- The image patches [Slurm]'s completion profile script so non-interactive shells
  do not fail before [QFw] SSH and [PRRTE] startup paths run.
- The Compose stack shares `/root/.ssh` across [Slurm] containers and starts
  `sshd`, so root-to-root SSH between containers works for [QFw] launch paths.
- [QFw] does not require a shared host filesystem for all internal infrastructure
  paths, but some simulators may have their own file-sharing assumptions. For
  example, multi-rank [NWQ-Sim] statevector dumps expect the dump path to be
  visible to all MPI ranks.

</details>

## Troubleshooting

<details>
<summary>Common fixes</summary>

If `qfw-install.env` is missing:

```bash
./do_configure.sh
```

If Compose still uses an old mount path:

```bash
./do_restart.sh --force-recreate
```

If [Slurm] config changes are not visible inside the running containers:

```bash
./update_slurmfiles.sh slurm.conf gres.conf rest.conf cgroup.conf
```

If a mounted Python venv came from an older image:

```bash
./do_ssh.sh
rm -rf /workspace/qfw-container-base/venv
python3 -m venv /workspace/qfw-container-base/venv
```

If Docker cache is suspect:

```bash
./do_build.sh --force
./do_startup.sh
```

If you only need to see what a helper would run:

```bash
./do_configure.sh --dry-run
./do_build.sh --dry-run
./do_startup.sh --dry-run
./do_restart.sh --dry-run
```

</details>

<details>
<summary>SELinux hosts (Fedora, RHEL, Rocky, CentOS Stream)</summary>

The compose file mounts two host paths into every service, `QFW_CONTAINER_BASE`
and `shared-dir`. On a host with SELinux enforcing, a bind mount keeps whatever
label the host directory already carries, container processes run as
`container_t`, and access is denied:

```text
$ podman exec -ti slurmctld ls -l /workspace/qfw-container-base
ls: cannot open directory '/workspace/qfw-container-base': Permission denied
```

Both mounts therefore carry the `:z` suffix, which asks the container runtime to
relabel those directories as shared container content. It is `:z` rather than
`:Z` because eleven services mount the same two paths, and `:Z` would give each
service a private label and lock the others out. Nothing is required on your
side. The suffix is ignored on hosts without SELinux, so macOS, Debian, and
Ubuntu are unaffected.

This failure is worth recognising because it does not announce itself.
`do_qfw_build.sh` looks for the [QFw] checkout with a `[ -f ]` test, and that test
is false whether the file is missing or merely unreadable. An unlabelled mount is
therefore reported as a missing checkout:

```text
No CMakeLists.txt in /workspace/qfw-container-base/QFw.
This build needs a QFw checkout on the v0.1 release line or later.
```

Check that the mount is readable before going looking for a missing clone.

There are two cases where `:z` is not the right tool:

- Relabelling is recursive and happens in place. `QFW_CONTAINER_BASE` defaults to
  `./shared-dir` inside this repository, which is the intended target. Do not
  point it at your home directory or another broadly shared path.
- The filesystem has to support extended attributes. Relabelling fails on NFS and
  similar, so a shared directory on a network filesystem needs another approach.

In either case, remove the suffix and label a repository-local directory
yourself:

```bash
sudo semanage fcontext -a -t container_file_t "$(pwd)/shared-dir(/.*)?"
sudo restorecon -R shared-dir
```

`chcon -Rt container_file_t shared-dir` has the same immediate effect and is
useful for a one-off test, but it does not survive `restorecon` or a filesystem
relabel. When it is reverted the cluster fails exactly as above, with nothing to
connect the failure to a relabel that happened days earlier.

</details>

[DEFw]: https://github.com/openQSE/DEFw
[libfabric]: https://github.com/ofiwg/libfabric
[NWQ-Sim]: https://github.com/pnnl/NWQ-Sim
[OpenMPI]: https://github.com/open-mpi/ompi
[PRRTE]: https://github.com/openpmix/prrte
[QDMI]: https://pypi.org/project/iqm-qdmi/
[QFw]: https://github.com/openQSE/QFw
[QRMI]: https://github.com/qiskit-community/qrmi
[Slurm]: https://github.com/SchedMD/slurm
[TNQVM]: https://github.com/ornl-qci/tnqvm
