# Build and Start the QFw Slurm Cluster

Use this recipe to create a complete cluster from the repository's selected
QFw and qfw-slurm release branches.

## Prerequisites

- Docker and Docker Compose are installed on the host.
- The current checkout is on the intended cluster branch.
- The host can fetch the configured QFw and qfw-slurm repositories.

## Build

Run from the cluster checkout:

```bash
cd /path/to/QFw-SLURM-Cluster
git switch release/v0.1

./do_configure.sh
./do_build.sh
```

`do_configure.sh` records the image and shared-mount settings in
`qfw-install.env`. `do_build.sh` installs Slurm, MUNGE, QFw, qfw-slurm,
libfabric, Open MPI, NWQSim, and TNQVM in the image.

## Start

```bash
./do_startup.sh
```

Startup creates the containers, configures the three non-root users, and
registers the cluster with SlurmDBD. It does not start the site directory or
QPMd services.

## Verify

```bash
./do_ssh.sh
sinfo -N -o '%N %P %t %f %c'
exit
```

The output must include application nodes `c1` through `c8`, three NWQSim
service nodes, and `iqm-head`. Every node should report four CPUs. Application
nodes belong to `normal`; service nodes belong to `qfw-services`.

Continue with [Start all site services](start-all-site-services.md), or use an
individual QPM recipe while debugging.

## Stop or Recreate

Stop containers while retaining named volumes:

```bash
./do_stop.sh
```

After rebuilding the image, recreate existing containers:

```bash
./do_restart.sh --force-recreate
```

Remove containers and named volumes only when a clean Slurm state is required:

```bash
./do_stop.sh delete
```
