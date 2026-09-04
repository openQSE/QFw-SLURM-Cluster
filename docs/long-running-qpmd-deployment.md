# Long-running QPMd Deployment

## Purpose

This document defines the deployment model used to test a privileged,
long-running QPM service with applications owned by several unprivileged
users. The model supports isolation testing inside the Docker Slurm cluster
without placing provider credentials in application environments.

The root account owns the directory service, optional PRTE DVM, and QPMd.
Regular users own their Slurm jobs and QFw application runtime state. Stopping
an application does not stop the site-owned service plane.

## Service Node Topology

Slurm manages eight ordinary application nodes and four dedicated service
hosts. The `normal` partition contains `c1` through `c8`. The visible
`qfw-services` partition contains the following administrator-only nodes:

| Node | Role |
| --- | --- |
| `nwqsim-head` | NWQSim QPMd and PRTE DVM master |
| `nwqsim-worker-1` | NWQSim DVM worker |
| `nwqsim-worker-2` | NWQSim DVM worker |
| `iqm-head` | IQM QPMd and provider client |

Every service host runs `slurmd` and participates in the same MUNGE trust
domain as the controller and application nodes. Static node features include
the owning QPM service ID. This allows `qfw-sinfo` to retain a `DOWN` row when
the QPM is absent from the directory.

Regular users cannot submit work to `qfw-services`. Application allocations
therefore consume classical nodes and logical QPM capacity independently.
Several allocations can reserve slices of one QPM when its admission policy
permits that sharing.

## Cluster Users

The cluster provides three regular test users with stable identities.

| User | UID | GID | Home | Sudo |
| --- | ---: | ---: | --- | --- |
| `user-a` | 1101 | 1101 | `/workspace/home/user-a` | None |
| `user-b` | 1102 | 1102 | `/workspace/home/user-b` | None |
| `user-c` | 1103 | 1103 | `/workspace/home/user-c` | None |

Each account uses Bash as its login shell and has a locked password. The same
username, UID, GID, home path, and shell must exist in `slurmctld`, `slurmdbd`,
`slurmrestd`, and compute containers `c1` through `c8`.

Slurm accounting contains one test account and an association for each user.
The association makes the test account the user's default Slurm account.

## Shared Homes

The host directory `${QFW_CONTAINER_BASE}/home` is mounted at
`/workspace/home` in every QFw cluster container. `/workspace` is not shared
unless a subdirectory is mounted there explicitly. The dedicated home mount
makes login state, application files, and heterogeneous-run coordination
visible at the same pathname on every node.

The shared home root is owned by root with mode `0755`. Each user home is owned
by its user with mode `0700`. This prevents one regular user from traversing
another user's files while allowing root to administer the environment.

Users create QFw application runs beneath their own homes. No administrator-
created per-user directory is needed under the global
`/workspace/qfw-container-base/qfw-runs` path.

## Login Environment

The account database and `do_ssh.sh --user USER` set `HOME` to the shared home
path and start the shell there. Each test user receives these convenience
variables:

```bash
export QFW_INSTALL_PREFIX=/opt/openqse/qfw
export QFW_VENV=/opt/openqse/qfw-venv
export QFW_SHARED_ROOT=/workspace/qfw-container-base
export QFW_RUN_BASE_DIR="${HOME}/qfw-runs"
export QFW_SITE_CONFIG=/etc/openqse/qfw/site.yaml
```

The login setup creates `${QFW_RUN_BASE_DIR}` as the owning user. Activation
then uses the installed QFw and Python environment:

```bash
source "${QFW_INSTALL_PREFIX}/bin/qfw-activate" \
  --venv "${QFW_VENV}"
```

`qfw-activate` supplies `QFW_PREFIX`, `DEFW_PREFIX`, `QFW_SHARE_DIR`, `PATH`,
`MANPATH`, and `VIRTUAL_ENV`. Allocation-specific values such as simulator
hosts, Slurm node lists, DVM URIs, and QPM endpoints remain runtime-managed.
Provider credentials are never exported to application users.

## Site Configuration

The cluster provisions three site-owned configuration files:

```text
/etc/openqse/qfw/site.yaml
/etc/openqse/qfw/device/device-access.yaml
/etc/openqse/qfw/device/qpu-users.json
```

`site.yaml` is client-readable and contains no provider secret. It selects the
directory-service connection record, the site service manifest, the protected
device-access file, and common QPM policy. Its device-access setting is:

```yaml
service:
  manifest: ${QFW_PREFIX}/share/qfw/config/services/site-services.yaml
  device-access-config: /etc/openqse/qfw/device/device-access.yaml
```

The file also publishes the directory-service connection record through the
existing shared coordination root:

```yaml
directory-service:
  name: qfw-site-dirsvc
  listen-port: 8090
  connect-timeout-seconds: 300
  connection-file: ${QFW_SHARED_ROOT}/qfw-site-services/directory-service.json
```

Applications may read `site.yaml` and the generated connection record. They do
not need access to the QPM manager run directory, DVM URI, device-access file,
or credential database.

## Device Access

`device-access.yaml` maps the logical service-manifest device ID to the IQM
provider endpoint and credential database. The installed configuration is:

```yaml
qpus:
  ornl-iqm-20q:
    provider: iqm
    provider-device-id: default
    url: https://qccsw.ccs.ornl.gov/
    credential-db: qpu-users.json
```

The relative credential path resolves beside `device-access.yaml` as
`/etc/openqse/qfw/device/qpu-users.json`.

## Credential Database

The installed credential database contains records for all three test users.
Empty API-key values are deliberate. QFw treats them as missing credentials,
which prevents an unconfigured deployment from authenticating with a literal
placeholder.

```json
{
  "users": {
    "user-a": {
      "enabled": true,
      "devices": {
        "ornl-iqm-20q": {
          "enabled": true,
          "api_key": ""
        }
      }
    },
    "user-b": {
      "enabled": true,
      "devices": {
        "ornl-iqm-20q": {
          "enabled": true,
          "api_key": ""
        }
      }
    },
    "user-c": {
      "enabled": true,
      "devices": {
        "ornl-iqm-20q": {
          "enabled": true,
          "api_key": ""
        }
      }
    }
  }
}
```

CI replaces the empty values through its secret-management mechanism before
the root-owned IQM QPM starts. Keys are never committed, included in an image,
printed in logs, or exported to a user process. Provisioning creates the
default file only when it is absent and never overwrites an existing database.

## Ownership and Permissions

The expected permissions are:

| Path | Owner | Mode | Readers |
| --- | --- | ---: | --- |
| `/etc/openqse/qfw` | `root:root` | `0755` | All users |
| `/etc/openqse/qfw/site.yaml` | `root:root` | `0644` | All users |
| `/etc/openqse/qfw/device` | `root:root` | `0700` | Root only |
| `device-access.yaml` | `root:root` | `0600` | Root only |
| `qpu-users.json` | `root:root` | `0600` | Root only |
| `/workspace/home/user-*` | Corresponding user | `0700` | Owner and root |

The root-owned QPM reads device configuration and binds a reservation to the
credential record for the submitting user. The application receives QFw
results and non-secret metadata, not the API key.

## Provisioning Without an Image Rebuild

User and configuration provisioning is an idempotent cluster-startup action.
A repository-managed user definition is the single source for usernames,
numeric IDs, home paths, shells, and Slurm associations.

The implementation uses `config/qfw-users.conf` for those identities and
`tools/provision-qfw-cluster.sh` for provisioning. The same tool installs the
defaults under `config/` only when the corresponding site or protected file is
absent. It therefore preserves API keys or other operator changes already
present in a running container.

The startup workflow performs these operations:

1. Mount `${QFW_CONTAINER_BASE}/home` at `/workspace/home` in each QFw
   container.
2. Create or validate the Linux groups and users in every QFw container.
3. Initialize shared homes and login environments without replacing user data.
4. Install missing site configuration and empty credential defaults without
   replacing an existing credential database.
5. Create or validate the Slurm test account and user associations.

Adding the shared-home mount requires Docker Compose to recreate the affected
containers. It does not require rebuilding the QFw cluster image. Ordinary
container restarts retain the identities. If containers are deleted and
recreated, the canonical `do_startup.sh` workflow provisions them again.

`do_ssh.sh` continues to enter `slurmctld` as root by default. Its user option
selects a regular account, the matching home directory, and the correct `HOME`:

```bash
./do_ssh.sh --user user-a
```

## Operational Flow

The operator enters the controller as root, activates QFw, and starts the site
directory and long-running QPM. CI injects IQM credentials before the hardware
QPM starts. A regular user then enters through `do_ssh.sh --user`, requests a
Slurm allocation, activates QFw, and runs an example in site service mode.

The cluster provides one root command for the complete site service plane:

```bash
qfw-site-services start
qfw-site-services status
```

Startup creates the directory on `slurmctld`, starts one PRTE DVM across the
three NWQSim hosts, and starts the NWQSim and IQM QPMs. The command waits for
manager readiness and gateway connectivity. Run `man 8 qfw-site-services` for
its configuration and failure behavior.

```bash
cd "${QFW_SHARE_DIR}/examples"
./qfw_run_all.sh --service-mode site --backend nwqsim
```

Users inspect service and active allocation state after activation:

```bash
qfw-sinfo
qfw-squeue
```

The corresponding references are `qfw-sinfo(1)` and `qfw-squeue(1)`.

For IQM validation, the user selects the IQM backend and the bounded test
approved by the CI workflow. Application teardown removes state beneath that
user's `QFW_RUN_BASE_DIR`. Only the root operator stops the long-running
directory service, DVM, or QPM.

## Validation

Deployment validation must confirm:

- Every QFw container resolves the same UID, GID, home, and shell for all three
  users.
- Each user authenticates through Munge and can use `salloc`, `srun`, and
  `sbatch`.
- Slurm records the correct user and account association for every job.
- Shared homes and QFw run directories are visible from heterogeneous groups.
- One user cannot traverse or modify another user's home or QFw runtime.
- Application users cannot read device access, credentials, or root-owned QPM
  state.
- Application users can read the site configuration and directory connection
  record.
- A root-owned long-running QPM remains alive across application teardown.
- Multiple users can reserve and execute against the same QPM without sharing
  application runtime or reservation state.

## Recovery

Run `qfw-site-services status` before restarting any component. A stale QPM or
directory manager record remains under `/var/lib/qfw-site-services` on the
host that owns it. The QFw manager reports stale process state and refuses to
replace a live instance.

Use `qfw-site-services stop` to unwind the service plane in dependency order.
It stops both QPMs before the directory and terminates the NWQSim DVM with its
recorded URI. If a host is unavailable, recover that host and repeat `stop`.
Do not delete manager state while a recorded process remains alive.

After host recovery, run `start` and confirm service registration with
`qfw-sinfo`. A restarted QPM has a new runtime identity and a later in-memory
directory generation. Slurm nodes that remain `DOWN` should be resumed only
after their `slurmd`, MUNGE identity, CPU count, and memory agree with
`slurm.conf`.

Protected IQM files are independent from generated manager state. Recovery
must preserve `/etc/openqse/qfw/device` ownership, permissions, and contents.
