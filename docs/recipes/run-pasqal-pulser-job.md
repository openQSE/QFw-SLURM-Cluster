# Run a Pulser Job on a Pasqal Device

This recipe runs QFw's Pulser example on Pasqal Cloud:
Pasqal's EMU_FREE emulator by default, or the FRESNEL QPU. It uses the
developer override, so it needs no QFw release.

The example starts a job-owned shim QPM for the Pasqal device, reserves it,
and runs one Pulser program through Pulser's own `QPUBackend` with
`qfw_pulser.QFwConnection`. The program fetches the device's specifications
through the QPM, places atoms on a calibrated layout, and runs two jobs: a
pi/2 pulse (each atom excited about half the time) and a pi pulse (every
atom flipped).

## Prerequisites

- The cluster is built and started from this branch (main once it merges),
  not `release/v0.1`, whose `do_qfw_build.sh` does not install Pulser; see
  [Build and start the cluster](build-and-start-cluster.md). The image's
  QFw does not matter for the developer build below.
- A Pasqal Cloud account with a project. A free account from the
  [Pasqal User Portal](https://portal.pasqal.cloud/) includes EMU_FREE; the
  portal's **Projects** page shows the project ID. On the Docker host, put
  the login in `~/.pasqal/config` (the file pasqal-cloud and QRMI read):

  ```ini
  username=you@example.com
  password=...
  project_id=...
  ```

  or export `PASQAL_USERNAME`, `PASQAL_PASSWORD` and `PASQAL_PROJECT_ID`
  instead. To use a token, export `PASQAL_TOKEN`: it takes precedence over
  the login. Pasqal's `pasqal-cloud` SDK (`pip install pasqal-cloud`) gets
  one from your login, and prompts for the password:

  ```bash
  export PASQAL_TOKEN="$(python3 -c 'from pasqal_cloud import SDK
  print(SDK(username="you@example.com").user_token())')"
  ```

  A `token=` in the file is used only when there is no username and
  password. Nothing from it is written into the shared mount; see
  [Credentials](#credentials).
- `python3` on the Docker host.

## Build QFw

From the cluster repository on the Docker host:

```bash
git clone --recursive https://github.com/openQSE/QFw.git shared-dir/QFw
git clone https://github.com/munich-quantum-toolkit/core.git shared-dir/mqt-core

./do_qfw_build.sh --clean
```

`do_qfw_build.sh` installs `setup/pulser-requirements.txt` (pulser-core) into
the developer venv because the checkout has it.

## Run on EMU_FREE

```bash
test_scripts/pasqal/run_pulser_example.sh
```

The script reads your login, allocates one application group
and one service group in `slurmctld`, activates the developer build and runs
`examples/qfw_pulser.sh`. It prints the allocation, the QPM the reservation
picked, any error lines and the results; the full log is
`pulser-<time>.log` in the current directory, printed at the end of every
run. The allocation is limited to two hours, and Ctrl-C cancels it. Expected
(EMU_FREE, 100 shots per job):

```
[slurm] Granted job allocation 3
[qfw]   reserved QPM shim-pasqal-...
Pulser program on 4 atoms, 100 shots per job, built on FRESNEL_CAN1
  QRMI  DONE      69.3s
          500 ns  excited 0.52  1011:13  1001:10
         1000 ns  excited 1.00  1111:100
```

EMU_FREE emulates the real devices, so the program is built on one of them,
FRESNEL_CAN1 by default (`--build-on`). Its 60-trap layout takes any number
of atoms; four are placed at least 15 um apart, so they do not interact.

## Run on the FRESNEL QPU

```bash
test_scripts/pasqal/run_pulser_example.sh --device-id pasqal-fresnel --atoms 42
```

FRESNEL's layout has 120 traps and must be at least 35% filled, so the
program needs 42 atoms. They sit 5 um apart and block each other's
excitation, so the excited fraction after the pi pulse stays well below 1.
The run submits two QPU jobs and waits for them in Pasqal's queue for up to an
hour (`job-timeout-seconds` in the device config).

Other options go to `examples/qfw_pulser.sh`, for example `--shots 500`. Run
`examples/qfw_pulser.sh --help` in the QFw checkout for the list.

## What Runs Where

| Step | Where |
| --- | --- |
| `pasqal_login.py` | Docker host, as you |
| `salloc` (two groups) | `slurmctld` |
| `qfw-setup`: directory service, shim QPM for the device | service group |
| `test_pulser.py` with `QFwConnection` | application group |
| QRMI `PasqalCloud` resource, Pasqal Cloud API calls | shim QPM |

The device definitions are `examples/qfw_pulser_device_access.yaml` in the
QFw checkout: `pasqal-emu-free` (EMU_FREE) and `pasqal-fresnel` (FRESNEL),
both through QRMI with a `no-secret` credential provider. `qfw_pulser.sh`
fills in the project.

## Credentials

QFw opens the Pasqal device with QRMI's `QuantumResource.from_config`, which
reads neither the environment nor `$HOME`, so the QPM does not pick up a
`~/.pasqal/config` on its own. Whose identity a job runs as depends on the
reservation's credential (design doc `docs/design/pulser-programs.md` in the
QFw checkout, Section 4):

- A credential carrying a token (a user's `api_key` in a credential DB): the
  job runs as that user, and the service's own login is never added.
- No token, as with the `no-secret` provider this example uses: the job runs
  as the QPM service, with the login the service was given. That is
  `QFW_API_KEY`, a service account
  (`<DEVICE>_QRMI_PASQAL_CLOUD_CLIENT_ID` and `_CLIENT_SECRET`), or, set
  explicitly, `PASQAL_CONFIG_ROOT` (a directory holding `.pasqal/config`) or
  `PASQAL_USERNAME`/`PASQAL_PASSWORD`.

The project is the reservation's, else the device's `project-id`, which
`qfw_pulser.sh` fills in from `QFW_PASQAL_PROJECT_ID`.

`run_pulser_example.sh` gives the service your login. `pasqal_login.py`
reads it on the Docker host and writes `PASQAL_USERNAME`, `PASQAL_PASSWORD`
and `QFW_PASQAL_PROJECT_ID` to an owner-only file in a private temporary
directory. The script passes that file to `docker exec --env-file`, so the
login never appears on a command line, and deletes it when the run ends. It
is never written into `shared-dir`. QRMI logs in with it and renews the token
as it expires, so a long FRESNEL queue does not outlive it.

With an exported `PASQAL_TOKEN`, or a `token=` and no username and password,
the script passes the token as `QFW_API_KEY` instead. QRMI cannot renew a
token, which is fine for one short run. Tokens in a credential DB are not
renewed either.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `no Pasqal Cloud login` | No username/password, token or `~/.pasqal/config` on the host. |
| `auth token is missing or expired and refresh credentials are not configured` | The run used a token (an exported `PASQAL_TOKEN`, or `token=` without a username and password), and it expired; unset `PASQAL_TOKEN` and rerun with a username and password, which QRMI renews from ([Credentials](#credentials)). |
| `422 ... exceeds the maximum number of atoms supported by this device (12)` | EMU_FREE takes at most 12 atoms; the 42-atom FRESNEL program cannot run on it. |
| `QRMI job ... timed out after ... and it was stopped` | The Pasqal queue was longer than the device's `job-timeout-seconds`; the job was cancelled. |
| `QPM reads ..., not Pulser sequences` | The reservation picked a non-Pasqal QPM; check `--device-id`. |
| `No module named 'pulser'` | The QFw checkout predates its Pulser frontend, the cluster checkout lacks this branch's `do_qfw_build.sh`, or the venv predates either; rerun `./do_qfw_build.sh --clean`. |

## Run on the Image's QFw

To test the QFw installed in the image instead, build the image from QFw
main (the default `--qfw-ref`) and pass `--image-install`:

```bash
./do_configure.sh
./do_build.sh
./do_restart.sh --force-recreate
test_scripts/pasqal/run_pulser_example.sh --image-install
```
