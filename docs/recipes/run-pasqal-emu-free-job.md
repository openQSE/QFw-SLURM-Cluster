# Run a Pulser Job on Pasqal EMU_FREE

`pasqal-emu-free` is Pasqal Cloud's free emulator as a site device: a shim QPM
on `pasqal-head` opens it through QRMI's `PasqalCloud` resource, and a job
reserves it with `--qpu=pasqal-emu-free` like any other site QPM. The QPM runs
as the service, with the operator's Pasqal login, and admits a user by the
enabled entry for the device in `config/qpu-users.json`. The user needs no
Pasqal account.

The QPM is opt-in: `qfw-site-services start` (target `all`) does not start it,
because it needs that login.

## Prerequisites

- A cluster whose containers come from a `docker-compose.yml` with
  `pasqal-head`: `./do_startup.sh` on a new cluster; on an existing one
  `./do_restart.sh --force-recreate` and then `./do_startup.sh`, which
  refreshes `slurm.conf` in the `etc_slurm` volume and provisions the node.
  The site services are up ([Start all site services](start-all-site-services.md)).
- A Pasqal Cloud account with a project. A free account from the
  [Pasqal User Portal](https://portal.pasqal.cloud/) includes EMU_FREE; the
  portal's Projects page shows the project ID, a UUID.

## Give the QPM Its Login

The QPM reads `.pasqal/config` under `PASQAL_CONFIG_ROOT`, which is
`/mnt/pasqal` in the containers and `shared-dir/pasqal` on the Docker host.
QRMI logs in with the username and password and renews the token itself, so
the file holds a login rather than a token, and its `project_id` is the
project the jobs are billed to. On the Docker host:

```bash
install -d -m 0700 shared-dir/pasqal/.pasqal
install -m 0600 /dev/null shared-dir/pasqal/.pasqal/config
cat > shared-dir/pasqal/.pasqal/config <<'EOF'
username=you@example.com
password=...
project_id=...
EOF
```

`shared-dir/pasqal/` is gitignored. Inside the containers root reads the
file. On a Linux host the mode keeps cluster users out; Docker Desktop's
virtiofs mount on macOS does not enforce file modes, so there every cluster
user can read it, as they can `shared-dir/iqm-creds.json`. Nothing from it
reaches a job, which sees its reservation and not the login.

## Start the QPM

From the Docker host:

```bash
docker exec slurmctld qfw-site-services start --target pasqal
docker exec slurmctld qfw-site-services status --target pasqal
```

`QFW_PASQAL_NODE` names another node and `PASQAL_CONFIG_ROOT` another
directory, for example on a cluster whose containers predate `pasqal-head`:

```bash
docker exec -e QFW_PASQAL_NODE=aws slurmctld qfw-site-services start --target pasqal
```

## Run a Pulser Job

Inside `slurmctld` as a cluster user (`./do_ssh.sh --user user-a`):

```bash
salloc --account=qfw-test --partition=normal --nodes=1 --ntasks=1 \
  --time=00:20:00 \
  --qpu=pasqal-emu-free \
  --workload-kind=quantum \
  --circ-count=2 \
  --max-qubits=4 \
  --max-depth=1 \
  --max-shots=100
```

Inside the allocation:

```bash
source "${QFW_INSTALL_PREFIX}/bin/qfw-activate" --venv "${QFW_VENV}"
qfw-setup --site-config "${QFW_SITE_CONFIG}"
qfw-srun --ntasks 1 "${QFW_SHARE_DIR}/examples/tests/test_pulser.py" \
  qrmi 100 4 FRESNEL_CAN1
qfw-teardown
qfw-deactivate
exit
```

The arguments are the shim library, the shots per job, the atoms, and the
real device whose specifications the program is built on: EMU_FREE emulates
the real devices, and FRESNEL_CAN1's layout takes any number of atoms up to
the 12 EMU_FREE accepts. `qfw-setup` with the site config creates the
runtime state that points the application at the site directory, `qfw-srun`
gives the step that environment and its SPANK callback obtains
`QFW_RESERVATIONS` from the gateway (a plain `srun` finds no directory
service), and `qfw-teardown` removes the state. The program picks the
reserved Pasqal QPM from the reservation, places the atoms, and runs a pi/2
pulse and a pi pulse. Expected, in about a minute plus Pasqal's queue:

```
Pulser program on 4 atoms, 100 shots per job, built on FRESNEL_CAN1
  QRMI  DONE      63.5s
          500 ns  excited 0.45  0000:12  0010:9
         1000 ns  excited 1.00  1111:100
```

## Notes

- Jobs run under the service's login and are billed to the config file's
  project. A `project_id` in a user's `pasqal-emu-free` entry in
  `qpu-users.json` bills that user's project instead.
- `job-timeout-seconds` for the device in `config/device-access.yaml` (1800)
  bounds the wait in Pasqal's queue; a job past it is cancelled.
- `docker exec slurmctld qfw-site-services stop --target pasqal` stops the
  QPM; `stop` on target `all` stops it too when it is running.
- The device runs through QRMI. QFw#182 adds a QDMI path for Pasqal
  (`pasqal-qdmi`, installed by `setup/qdmi-requirements.txt`); once an image
  carries it, adding `qdmi` to the device's `libraries` in
  `config/device-access.yaml` offers both. The native library reads the same
  login file through `PASQAL_AUTHFILE`, which `qfw-site-services` already
  forwards.

| Piece | Where |
| --- | --- |
| the `pasqal-head` node | `docker-compose.yml`, `slurm.conf`, `tools/provision-qfw-cluster.sh` |
| device `pasqal-emu-free` and its entitlement provider | `config/device-access.yaml` |
| service `shim-pasqal-emu-free` | `config/site-services.yaml` |
| `--qpu=pasqal-emu-free` | `config/qfw-slurm/resources.lua`, `config/qfw-slurm/plugin.conf` |
| user entitlements | `config/qpu-users.json` |
| `--target pasqal` | `tools/qfw-site-services` |
