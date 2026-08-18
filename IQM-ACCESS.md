# Running the containerized cluster against the IQM QPU

How to point this SLURM cluster at the real ORNL IQM 20-qubit system and run the
QRMI/QDMI shim smoke tests against it.

Everything here assumes the cluster already builds and starts — see
[README.md](README.md) — and that `shared-dir/QFw` is checked out. For the
credential-free routing checks that need no hardware at all, see
[TESTING.md](TESTING.md).

## Which path applies to you

| | On the ORNL network | Remote |
|---|---|---|
| IQM endpoint reachable directly | yes | no |
| SSH tunnel needed | no | yes |
| Compose overlays | `docker-compose.iqm.yml` | that **plus** `docker-compose.iqm-tunnel.yml` |
| `url:` in the device-access file | `https://qccsw.ccs.ornl.gov` | `https://qccsw.ccs.ornl.gov:8443` |

Most users are on the ORNL network and can skip [step 3](#3-remote-only-open-the-ssh-tunnel).

`qccsw.ccs.ornl.gov` is not in public DNS. Off-site, name resolution fails
before any connection is attempted, which is what the tunnel overlay fixes.

> **Do not apply the tunnel overlay on the ORNL network.** It overrides DNS for
> the IQM host and points it at the Docker host gateway, breaking a connection
> that would otherwise work.

## 1. Get an API token

Generate a personal API token from the IQM web interface for your account.

<!-- Replace with the exact URL and menu path for the ORNL IQM web UI. -->

Treat it like a password. It grants job submission against a shared instrument,
and it is not scoped per project.

Put it in your shell without it landing in shell history:

```bash
read -rs QFW_API_KEY && export QFW_API_KEY
```

Paste, press Enter. Nothing is echoed. The rest of this guide assumes it is
exported in the shell you are working in.

## 2. Give the token to QFw

Two files, both **gitignored**. Do not put your token anywhere else — in
particular not in `shared-dir/QFw/services/dev-config/qpu_users.json`, which is
a tracked file in the QFw repository.

### The credential file

```bash
python3 -c 'import json,os;json.dump({"users":{"root":{"devices":{"ornl-iqm-20q":{"api_key":os.environ["QFW_API_KEY"]}}}}},open("shared-dir/iqm-creds.json","w"),indent=2)' && chmod 600 shared-dir/iqm-creds.json
```

This reads the token from the environment, so it never appears on a command
line. `root` is the user the service resolves to inside the container; QFw picks
it from `QFW_USER`, `SLURM_JOB_USER`, `SLURM_USER`, `USER`, `LOGNAME`, then
`whoami`.

### The device-access file

```bash
cp shared-dir/iqm-device-access.yaml.example shared-dir/iqm-device-access.yaml
```

Edit it if you are remote — the `url:` needs the tunnel port. The example is
commented with both forms.

Create this file **before** the first `docker compose up`. If the host path is
missing, Docker creates a *directory* there and the services fail with a
confusing config-parse error.

### Why a file rather than environment variables

This is the part that surprises people. QFw's PRTE launcher starts the QPM
service with:

```
ssh <node> 'export QFW_RUN_ID=...; export QFW_ALLOCATION_MODE=...; export QFW_GROUP_*; ...'
```

Only those variables cross that boundary. `QFW_QC_URL` and `QFW_API_KEY` passed
to `docker exec -e` reach a `sbatch` job but **not** a DEFw service launched
over PRTE. So:

- **the introspection sbatch and anything else running inside the container**
  read `QFW_DEVICE_ACCESS_CFG`, which `docker-compose.iqm.yml` sets
- **a long-running service-plane QPM** does not see it, and resolves credentials
  through the installed site config instead

Set up both and neither case surprises you.

> **Changed on the v0.1 line.** This overlay used to bind-mount the
> device-access file over the image's baked `services/dev-config/config.yaml`.
> The image no longer bakes QFw, and `dev-config` is deliberately excluded from
> the install tree, so that mount is gone and `QFW_DEVICE_ACCESS_CFG` replaces
> it. The service-plane half, `service.device-access-config` in
> `$QFW_PREFIX/share/qfw/config/site.yaml`, is **not wired up yet**.

Your device-access file must carry a `provider:` key. Device selection now
matches on provider first, and the old "just use the single configured QPU"
fallback is gone, so a file without it fails with *does not define a QPU for
provider 'iqm'*.

## 3. Remote only: open the SSH tunnel

The hub node is the only host with a route to the IQM system. It needs no
software installed — SSH port forwarding is implemented by `sshd` itself.

```bash
cp iqm-tunnel.env.example iqm-tunnel.env
```

Set `HUB` to your `user@hub-hostname`. `IQM_HOST` already points at the ORNL
q20. Then, in its own terminal:

```bash
./iqm-tunnel.sh
```

Leave it running. It listens on `0.0.0.0:8443` and forwards to the IQM endpoint
through hub, reconnecting if the connection drops.

Check it any time:

```bash
./iqm-tunnel.sh --check
```

`HTTP 401` means healthy — the endpoint answered and rejected an unauthenticated
request. Anything else means the tunnel is down.

If your hub login needs a passcode, the reconnect cannot answer it for you: the
script will sit at the prompt until you type it, and the tunnel stays down
meanwhile. **When something hangs or a device session fails to initialize,
check the tunnel first** — a dead tunnel surfaces deep inside QFw as errors that
look like code or device faults.

## 4. Start the cluster

> **New on the v0.1 line.** Starting the containers is no longer enough. The
> image ships build dependencies but not QFw itself, so after the stack is up
> you must build QFw and DEFw into the shared mount:
>
> ```bash
> ./do_qfw_build.sh
> ```
>
> That installs to `shared-dir/qfw-install`, which every node sees. Re-run it
> with `--skip-venv` after changing QFw source: the install tree is a copy, so
> edits under `shared-dir/QFw` do not take effect until you reinstall.

On the ORNL network:

```bash
docker compose --env-file qfw-install.env -f docker-compose.yml -f docker-compose.iqm.yml up -d
```

Remote, adding the tunnel overlay:

```bash
docker compose --env-file qfw-install.env -f docker-compose.yml -f docker-compose.iqm.yml -f docker-compose.iqm-tunnel.yml up -d
```

Confirm the config reached a compute node — you should see your `url:`,
`provider:` and `credential-db:`:

```bash
docker exec c5 sh -c 'echo "$QFW_DEVICE_ACCESS_CFG"; cat "$QFW_DEVICE_ACCESS_CFG"'
```

Then confirm the endpoint answers and your token works. This is read-only and
uses no QPU time:

```bash
docker exec -e QFW_API_KEY c5 bash -c 'curl -sS -H "Authorization: Bearer $QFW_API_KEY" https://qccsw.ccs.ornl.gov/api/v1/quantum-computers' | python3 -m json.tool
```

Remote users: add `:8443` to that URL. The single quotes matter — they let the
container's shell expand the token so it stays out of your history.

You should get one device, `alias: default`, display name `ORNL 20 qubit`. That
`alias` is what belongs in `provider-device-id`.

## 5. Introspection smoke (both libraries)

Runs device introspection through QDMI **and** QRMI and checks they agree.
Read-only — no circuit is submitted.

The live section is gated on the environment variables, so pass them here even
though execution does not use them:

```bash
docker exec -e QFW_QC_URL="https://qccsw.ccs.ornl.gov" -e QFW_API_KEY -w /workspace/qfw-container-base slurmctld sbatch shim-smoke.sbatch
```

Note the job id it prints, then read that file:

```bash
cat shared-dir/shim-smoke.<jobid>.out
```

Success looks like:

```
[shim-smoke] live qdmi -> qhw-device-v1 (20 qubits) + qhw-coupling-v1 (30 edges)
[shim-smoke] live qrmi -> qhw-device-v1 (20 qubits) + qhw-coupling-v1 (30 edges)
[shim-smoke] cross-library: QDMI and QRMI agree on qhw shape (20 qubits, 30 edges)

SHIM BIFURCATION + INTROSPECTION SMOKE: PASS
```

**20 qubits / 30 edges** is the real q20 topology. `live introspection: skipped`
instead means the environment variables did not arrive.

## 6. Execution smoke (a real circuit)

> **Not yet revalidated on the v0.1 line.** The commands below source
> `setup/qfw_activate`, which no longer exists, and `qfw_shim_smoke.sh` now
> resolves its QPM through the directory service and requires a reservation id
> and a site service manifest. Replacing `qfw_activate` with
> `$QFW_PREFIX/bin/qfw-activate` is not sufficient on its own. Treat this
> section as stale until the service plane is wired up and re-run.
>
> Execution itself is fine, and is exercised today by
> `examples/measure_shim_execution.py`, which drives the drivers in-process and
> returns `counts {'1': 10}` through QRMI, QDMI and the native client.

Submits a one-qubit circuit — `x q[0]` then measure — through the shim to the
QPU. No environment variables: this path reads the device-access file.

Start with QRMI, the descriptor's execution owner:

```bash
docker exec slurmctld salloc -N 1 -p quantum --gres=qpu:1 bash -c 'source /opt/qfw/qhpc/QFw/setup/qfw_activate && cd $QFW_PATH/examples && ./qfw_shim_smoke.sh --lib qrmi --call async_run --shots 10 --circuit-run-timeout 600'
```

Then the same through QDMI:

```bash
docker exec slurmctld salloc -N 1 -p quantum --gres=qpu:1 bash -c 'source /opt/qfw/qhpc/QFw/setup/qfw_activate && cd $QFW_PATH/examples && ./qfw_shim_smoke.sh --lib qdmi --call async_run --shots 10 --circuit-run-timeout 600'
```

`--circuit-run-timeout 600` allows for queueing behind other users; the default
of 100s was written for a mock. `--shots 10` keeps a first run small.

Both should end in `SHIM REMOTE QPM SMOKE: PASS` with `rc: 0` and:

```yaml
result:
  counts:
    '1': 10
```

An X gate on |0⟩ measured as `1`. On hardware expect mostly `1` with the
occasional `0` from readout error — **all** `0`s would mean something inverted
the circuit.

The two records agree on `counts`, `shots`, `num_circuits` and `schema`
(`qhw-result-v1`). They differ in provider detail by construction: QRMI echoes a
full `run_request` and carries `calibration.id` and `job.id`, while QDMI reports
`extensions: {}` and omits both — QDMI runs currently cannot be correlated with
the IQM-side job.

## Troubleshooting

**`Quantum computer alias 'ornl-iqm-20q' not found`** — `provider-device-id` is
missing or wrong in the device-access file, so QFw sent its own device id as the
IQM alias. Confirm the real alias with the `quantum-computers` query in step 4.

**`IQM dynamic architecture did not report active qubits`** — usually *not* a
device problem. QRMI's `target()` returns its key structure with empty values
when it cannot reach the server, so a connectivity failure surfaces as this.
Check the tunnel (`./iqm-tunnel.sh --check`) and the `url:` port.

**`failed to open the QDMI device session`** — same family: unreachable endpoint
or credentials that did not arrive. Verify step 4's two checks in order.

**`live introspection: skipped`** — the introspection sbatch did not receive
`QFW_QC_URL`/`QFW_API_KEY`. Confirm the token is exported:

```bash
docker exec -e QFW_API_KEY slurmctld bash -c 'echo "${QFW_API_KEY:+reached container (${#QFW_API_KEY} chars)}${QFW_API_KEY:-NOT SET}"'
```

**Execution fails while introspection passes** — the classic signature of
credentials reaching `sbatch` but not the service. Re-read
[step 2](#why-a-file-rather-than-environment-variables).

**Errors referencing code you already fixed** — only `svc_lib_qpm`,
This class of problem is much reduced on the v0.1 line: the container no longer
carries its own QFw clone, and `./do_qfw_build.sh` builds the checkout in
`shared-dir/QFw` directly. What can still drift is the **install tree** against
the source, because the install is a copy. Compare before theorizing:

```bash
docker exec c5 sh -c 'diff /workspace/qfw-container-base/QFw/services/util/iqm_transcode.py \
    "$(ls -d /workspace/qfw-container-base/qfw-install/lib*/qfw/services)"/util/iqm_transcode.py'
```

No output means source and install agree. Any difference means you edited the
source and have not reinstalled.

Rebuild the image with `./do_build.sh --force`, then rebuild QFw itself with
`./do_qfw_build.sh --clean`, to resynchronize.

## Keeping the token safe

`iqm-tunnel.env`, `iqm-device-access.yaml` and `iqm-creds.json` are all
gitignored. Only the `.example` templates are tracked. Before committing:

```bash
git status --short
```

None of those three should appear. The token grants job submission on a shared
instrument, so treat a leak as requiring rotation, not just a history rewrite.
