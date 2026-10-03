# Run QFw on the DEFw v2 Prototype

This recipe runs an installed QFw example with its QPM served on the DEFw v2
prototype, under Slurm, beside the v1 service plane. It is the prototype's W7
check. The v1 plane keeps running, and v1 runs are unaffected.

Only the directory, the NWQSim QPM and the fake IQM QPM run on v2. The
qfw-slurm gateway is a DEFw v1 client, so a v2 run reserves its QPM from the
example's own driver rather than through `salloc --qpu`.

## Prerequisites

- The cluster is running from an image whose `qfw-site-services --help`
  mentions `QFW_DEFW_VERSION=2`. `do_startup.sh` provisions the v2 plane's
  configuration, `/etc/openqse/qfw/site-defw2.yaml` and
  `/etc/openqse/qfw/services/site-services-defw2.yaml`.
- A QFw installation with DEFw v2 built in. QFw's `defw2-prototype` branch has
  it. Check that branch out in `shared-dir/QFw`, with its submodules, and build
  a developer override:

  ```bash
  ./do_qfw_build.sh --defw2
  ```

  An image can carry it instead. Build one with `QFW_REF=defw2-prototype` and
  `QFW_BUILD_DEFW2=ON` set for `do_build.sh`.

The commands below use the override in `shared-dir/qfw-install`. For an image
installation, use `/opt/openqse/qfw` and `/opt/openqse/qfw-venv` instead.

## Start the v2 Plane

From the Docker host:

```bash
docker exec \
  -e QFW_DEFW_VERSION=2 \
  -e QFW_INSTALL_PREFIX=/workspace/qfw-container-base/qfw-install \
  -e QFW_VENV=/workspace/qfw-container-base/qfw-venv \
  slurmctld /bin/bash -lc 'qfw-site-services start && qfw-site-services status'
```

The status ends with:

```text
QFw site services: UP

Directory: UP
NWQSim: UP
Fake IQM: UP
```

`QFW_DEFW_VERSION=2` selects the v2 plane. It reads
`/etc/openqse/qfw/site-defw2.yaml` and keeps its state under
`/var/lib/qfw-site-services-defw2`. Its directory listens on port 8190 and its
QPMs on 8494 for NWQSim and 8594 for the fake IQM, clear of v1's 8090, 8490
and 8590. It publishes its directory in
`${QFW_SHARED_ROOT}/qfw-site-services-defw2/directory-service.json`. Its `all`
target is those three, and it rejects the other targets.

Run `qfw-site-services` from a fresh login shell, as above. It reads
`QFW_SITE_CONFIG` from the environment, and `qfw-activate` exports one, so in a
shell where QFw is active it would start the v2 plane from v1's configuration.

## Run the Example

From the Docker host:

```bash
./do_ssh.sh --user user-a
```

Inside `slurmctld`:

```bash
salloc --partition=normal --nodes=1 --ntasks=1 --time=00:10:00
```

Inside the granted allocation:

```bash
export QFW_PREFIX=/workspace/qfw-container-base/qfw-install
export QFW_VENV=/workspace/qfw-container-base/qfw-venv
source "${QFW_PREFIX}/bin/qfw-activate" --venv "${QFW_VENV}"
export QFW_DEFW_VERSION=2
export QFW_SITE_CONFIG=/etc/openqse/qfw/site-defw2.yaml

cd "${QFW_SHARE_DIR}/examples"
./qfw_qiskit_simple.sh --service-mode site --backend nwqsim 4

qfw-deactivate
exit
```

The example prints its counts and its statevector, as it does on v1. Use
`--backend fake-iqm` for the fake IQM QPM.

Set `QFW_PREFIX` before activating. The image sets it to its own installation,
and `qfw-activate` keeps a prefix it finds, so without it the image's v1 QFw
runs. That fails with `Couldn't find a directory service`, because the
directory it is pointed at is a v2 one.

`QFW_DEFW_VERSION=2` runs the example's processes on v2, and the run records
the choice. `QFW_SITE_CONFIG` names the v2 plane, in place of the v1 plane's
configuration that the test users' profile sets.

To run the same example on v1 from the same installation, leave
`QFW_DEFW_VERSION` unset and keep the profile's `QFW_SITE_CONFIG`.

## Stop the v2 Plane

From the Docker host:

```bash
docker exec \
  -e QFW_DEFW_VERSION=2 \
  -e QFW_INSTALL_PREFIX=/workspace/qfw-container-base/qfw-install \
  -e QFW_VENV=/workspace/qfw-container-base/qfw-venv \
  slurmctld /bin/bash -lc 'qfw-site-services stop'
```

It stops the fake IQM QPM, the NWQSim QPM and then the directory. The v1 plane
is untouched.
