# Run QFw on the DEFw v2 Prototype

This recipe runs an installed QFw example with its QPM served on the DEFw v2
prototype, under Slurm, beside the v1 service plane. It is the prototype's W7
check. The v1 plane keeps running, and v1 runs are unaffected.

The v2 plane has the directory and the QPMs of the default plane: NWQSim, IQM,
the shim, IBM, AWS and the fake IQM. It has no gateway, because the qfw-slurm
gateway is a DEFw v1 client, so a v2 run reserves its QPM from the example's
own driver rather than through `salloc --qpu`. The opt-in QPMs have not been
tried on v2.

This recipe runs the two simulated QPMs. The IQM QPM and the shim QPM have
each run a circuit on the ORNL device through v2. The IBM and AWS QPMs start
and answer device queries there, and no circuit has been run through them.

## Prerequisites

- The cluster is running from an image built from this branch. Its QFw has
  DEFw v2 built in, and its `qfw-site-services --help` mentions
  `QFW_DEFW_VERSION=2`. `do_startup.sh` provisions the v2 plane's
  configuration, `/etc/openqse/qfw/site-defw2.yaml` and
  `/etc/openqse/qfw/services/site-services-defw2.yaml`.

The commands below use the image's installation, `/opt/openqse/qfw` and
`/opt/openqse/qfw-venv`. To run a QFw checkout instead, see
[Use a developer override](#use-a-developer-override).

## Start the v2 Plane

From the Docker host:

```bash
docker exec -e QFW_DEFW_VERSION=2 \
  slurmctld /bin/bash -lc 'qfw-site-services start && qfw-site-services status'
```

The status ends with:

```text
QFw site services: UP

Directory: UP
NWQSim: UP
IQM: UP
Shim: UP
IBM: UP
AWS: UP
Fake IQM: UP
```

`QFW_DEFW_VERSION=2` selects the v2 plane. It reads
`/etc/openqse/qfw/site-defw2.yaml` and keeps its state under
`/var/lib/qfw-site-services-defw2`. Its directory listens on port 8190, clear
of v1's 8090, and each QPM listens four ports above its v1 port: 8494 for
NWQSim against v1's 8490, for example. It publishes its directory in
`${QFW_SHARED_ROOT}/qfw-site-services-defw2/directory-service.json`. Its `all`
target is those seven, and it rejects the gateway and the opt-in targets.

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
salloc --account=qfw-test --partition=normal --nodes=1 --ntasks=1 --time=00:10:00
```

Inside the granted allocation:

```bash
source /opt/openqse/qfw/bin/qfw-activate --venv /opt/openqse/qfw-venv
export QFW_DEFW_VERSION=2
export QFW_SITE_CONFIG=/etc/openqse/qfw/site-defw2.yaml

cd "${QFW_SHARE_DIR}/examples"
./qfw_qiskit_simple.sh --service-mode site --backend nwqsim 4

qfw-deactivate
exit
```

The example prints its counts and its statevector, as it does on v1. Use
`--backend fake-iqm` for the fake IQM QPM.

`QFW_DEFW_VERSION=2` runs the example's processes on v2, and the run records
the choice. `QFW_SITE_CONFIG` names the v2 plane, in place of the v1 plane's
configuration that the test users' profile sets.

To run the same example on v1 from the same installation, leave
`QFW_DEFW_VERSION` unset and keep the profile's `QFW_SITE_CONFIG`.

## Stop the v2 Plane

From the Docker host:

```bash
docker exec -e QFW_DEFW_VERSION=2 \
  slurmctld /bin/bash -lc 'qfw-site-services stop'
```

It stops the QPMs and then the directory. The v1 plane is untouched.

## Use a Developer Override

To run the v2 plane and the example from a QFw checkout instead of the image's
installation, check QFw's `defw2-prototype` branch out in `shared-dir/QFw`, with
its submodules, and build the override with v2:

```bash
./do_qfw_build.sh --defw2
```

Then give both `docker exec` commands above the override's paths:

```bash
docker exec \
  -e QFW_DEFW_VERSION=2 \
  -e QFW_INSTALL_PREFIX=/workspace/qfw-container-base/qfw-install \
  -e QFW_VENV=/workspace/qfw-container-base/qfw-venv \
  slurmctld /bin/bash -lc 'qfw-site-services start && qfw-site-services status'
```

and activate the override in the allocation, in place of the image's
installation:

```bash
export QFW_PREFIX=/workspace/qfw-container-base/qfw-install
export QFW_VENV=/workspace/qfw-container-base/qfw-venv
source "${QFW_PREFIX}/bin/qfw-activate" --venv "${QFW_VENV}"
```

Set `QFW_PREFIX` before activating. The image sets it to its own installation,
and `qfw-activate` keeps a prefix it finds, so without it the image's QFw runs
instead of the override.
