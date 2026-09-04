# Persistent QFw Service Validation

This report records the 4 September 2026 validation of the persistent QFw
service topology and qfw-slurm allocation lifecycle on the virtual Slurm
cluster. The test began from a newly created Compose stack and an image built
from the committed `release/v0.1` branches.

## Validated revisions

| Component | Revision |
| --- | --- |
| DEFw | `8b253aea5e86ffface7ebfc98bbce066f2d20887` |
| QFw | `8851b0b748c3ac611aa5a503ed96870b59fbad52` |
| qfw-slurm | `3e17d5baef459c084a89baf7675e086b18847393` |
| QFw-SLURM-Cluster | `98f9211b88b2481ca995f3cb829be2657dce6435` |
| Container image | `sha256:22d8adcc3930e1311874d7b8a8e368ef7ee04a9688d63eff034fd53779c75af7` |

The image build resolved QFw and qfw-slurm from their upstream release
branches. QFw's bundled DEFw submodule resolved to the DEFw revision above.
The full runtime matrix used qfw-slurm `b2c51ee`; `3e17d5b` adds only the
completed implementation checklist. A final rebuild from `3e17d5b` repeated
the qfw-slurm build and 11-test installation suite, and all recreated
containers were verified against the final image ID above.
The protected IQM API key was injected only into the running `iqm-head`
container. Its value was not printed, copied into application state, or added
to an image layer.

## Cluster and service results

| Check | Result | Evidence |
| --- | --- | --- |
| Image build | PASS | NWQSim, CPU TNQVM, QFw, qfw-slurm, Lua plugins, and MUNGE built or installed successfully |
| Slurm topology | PASS | c1 through c8 and four service nodes reported four CPUs each |
| Service partition | PASS | `qfw-services` contained the IQM and three NWQSim nodes; none appeared in `normal` |
| Static configuration tests | PASS | `test_qfw_site_services.sh` and `test_qfw_service_topology.sh` passed |
| Site startup | PASS | One directory service, one NWQSim QPM, and one IQM QPM became ready |
| Duplicate startup | PASS | A second `qfw-site-services start` failed without disturbing running services |
| DVM membership | PASS | The DVM contained `nwqsim-head` and both NWQSim workers |
| Multi-host simulation | PASS | `test_qfw_nwqsim_dvm.sh` ran a two-host NWQSim operation through the DVM |
| Inspection commands | PASS | `qfw-sinfo --json` and `qfw-squeue --json` produced valid JSON as a non-root user |
| Manual installation | PASS | Manuals for `qfw-sinfo`, `qfw-squeue`, and `qfw-site-services` were discoverable |

The DVM includes all three NWQSim service nodes. The execution check uses two
hosts because the selected NWQSim MPI path requires a power-of-two rank count;
it still verifies that simulator execution crosses hosts.

## Allocation lifecycle results

| Case | Result | Observation |
| --- | --- | --- |
| Idle service | PASS | NWQSim and IQM reported `IDLE` with zero active reservations |
| Three concurrent users | PASS | user-a, user-b, and user-c ran on c1, c2, and c3; NWQSim reported `BUSY` and active count 3 |
| Cross-user inspection | PASS | `qfw-squeue` showed only Slurm-visible job identity and sanitized QPM state |
| Service-node isolation | PASS | No allocation consumed a node in `qfw-services` |
| Normal application | PASS | Job 4 ran the five-qubit Qiskit example through the scheduler-owned NWQSim reservation |
| Heterogeneous application | PASS | Heterogeneous job 5 used c1 and c2; both components received the identical reservation tuple |
| Repeated application use | PASS | Application steps reused the allocation reservation instead of creating another one |
| Normal completion | PASS | Jobs 1 and 2 completed and their gateway journal rows reached `released` |
| Cancellation | PASS | Job 3 was cancelled and its reservation reached `released` |
| QPM restart | PASS | NWQSim reported `DOWN`, IQM remained visible, and restart changed generation 1 to 2 and created a new runtime ID |

The normal and heterogeneous Qiskit runs both returned valid counts and a
terminal `status: ok` record. The service QPM and DVM remained running after
application teardown.

## Application results

The complete backend-compatible NWQSim aggregate suite ran as user-a against
the persistent site QPM.

| Example | Result |
| --- | --- |
| Initialization | PASS |
| Qiskit simple | PASS |
| GHZ with Qiskit | PASS |
| GHZ with PennyLane | PASS |
| PennyLane | PASS |
| QAOA | PASS |
| Qiskit VQE | PASS |
| SuperMarQ | PASS |
| Shim smoke | SKIP: requires the specialized local shim backend |
| Chemistry in aggregate runner | SKIP: validated separately against IQM |

A guarded real-IQM chemistry run then passed as user-a with five qubits and
16 shots. The driver emitted terminal success, the chemistry program completed,
and allocation 8 reached terminal release in the gateway journal.

## Shutdown and recovery results

`qfw-site-services stop` stopped the IQM QPM, NWQSim QPM, DVM, and directory
service in dependency order. The recorded PIDs were no longer live, no PRTE
process remained, and the DVM URI was removed. Persistent manager records are
retained as lifecycle history and do not represent running processes.

The isolated NWQSim stop/restart test also verified that an unavailable QPM
does not prevent `qfw-sinfo` from displaying the healthy IQM service. The
duplicate-start test exercised stale-manager protection before final shutdown.

## Commands used

The main validation entry points were:

```bash
./do_build.sh
./do_startup.sh
./test_scripts/test_qfw_site_services.sh
./test_scripts/test_qfw_service_topology.sh
docker exec slurmctld qfw-site-services start
./test_scripts/test_qfw_nwqsim_dvm.sh
```

Application allocations used the documented allocator options on `salloc` or
`sbatch`, including `--qpu`, `--workload-kind`, `--circ-count`,
`--max-qubits`, `--max-depth`, and `--max-shots`. Applications activated the
installed `/opt/openqse/qfw` environment and used `--service-mode site`.

## Retained gaps

- The native DEFw/QFw C client does not exist yet. qfw-slurm therefore retains
  QSGP, the gateway, and its journal as the documented first-release bridge.
- The native-path lifecycle suite and removal of the gateway remain deferred
  until that client is implemented and passes the same acceptance tests.
- TNQVM was built into the image, but runtime validation remains deprioritized;
  NWQSim is the supported simulator path exercised by this report.
