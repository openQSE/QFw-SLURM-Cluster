# Run a circuit against IBM Quantum System devices

This recipe shows how to run a quantum circuit against IBM Quantum System (IQS) devices through the QRMI library. It uses the `qsa-sim` simulator.

## 1. Using `qfw_ibm_qpm_site.sh`

This example shows an easy way of how you could create your own quantum
circuit and run it in QFw. `qfw_ibm_qpm_site.sh` is a simple tool, you
could just reuse it or create your own. The actual circuit is implemented in
`QFw/examples/tests/test_ibm_qpm.py`, which creates a parameterized circuit
and show how to pass parameters values as well as compilation options to the
QFw qrmi driver.

This is an end-to-end job execution with slurm and QFw. Slurm resource reservations go through the site QPM running in the `qsa-sim-head` container. More details in the [detailed QFw slurm workflow](https://github.com/openQSE/qfw-slurm/blob/main/docs/detailed-design-workflow.md).

### Prerequisites

- The `qsa-sim` is started and configured. Only the steps 1-3 from [start-ibm-qsa-sim.md](./start-ibm-qsa-sim.md) are required.

### Running the circuit

Connect to `slurmctld` as `user-a` and allocate resources for 10 min as below. That will grant you a reservation through the site QPM that is running in the container `qsa-sim-head`.

```bash
./do_ssh.sh --user user-a
salloc --partition=normal \
  --nodes=1 \
  --ntasks=1 \
  --time=00:10:00 \
  --qpu=ibm-fake-lagos \
  --workload-kind=quantum \
  --circ-count=1 \
  --max-qubits=5 \
  --max-depth=20 \
  --max-shots=1024 \
  --account qfw-test
```

Run the quantum circuit in the granted allocation.

```bash
export QFW_SHARED_ROOT=/workspace/qfw-container-base
# Uncomment the line below only if you want to use the QFw installed
# with "./do_qfw_build.sh" rather than the QFw that comes in the
# container image.
#export QFW_PREFIX=$QFW_SHARED_ROOT/qfw-install
source $QFW_INSTALL_PREFIX/bin/qfw-activate --venv $QFW_INSTALL_PREFIX/../qfw-venv
cd $QFW_SHARE_DIR/examples
./qfw_ibm_qpm_site.sh
```

The output of a successful run would include messages like below at the bottom. It would also include RESULT fields such as `metrics.counts` and circuit parameter values.

```text
QFW_EXAMPLE_RESULT {
  "args": [],
  "duration_sec": 15.0,
  "event": "finish",
  "example": "qsa-qpm-site",
  "kind": "wrapper",
  "rc": 0,
  "schema": "qfw-example-wrapper-v1",
  "status": "ok",
  "teardown_rc": 0,
  "timestamp_ns": 1792685729300869305
}
```
## 2. Using the `qfw_run_all.sh`

`qfw_run_all.sh` is a flexible tool to automate the execution of test cases in multiple configurations.

### Prerequisites

- The `qsa-sim` is started and configured. Only the steps 1-3 from [start-ibm-qsa-sim.md](./start-ibm-qsa-sim.md) are required.

### Running test examples

Connect to `slurmctld` as `user-a` and allocate resources for 10 min as below. Same as section 1, this is an end-to-end QFw slurm allocation.

```bash
./do_ssh.sh --user user-a
salloc --partition=normal \
  --nodes=1 \
  --ntasks=1 \
  --time=00:10:00 \
  --qpu=ibm-fake-lagos \
  --workload-kind=quantum \
  --circ-count=1 \
  --max-qubits=5 \
  --max-depth=20 \
  --max-shots=1024 \
  --account qfw-test
```

In the granted allocation, call `./qfw_run_all.sh` to run some test cases. Not all test cases are supported in all configurations yet.

```bash
./do_ssh.sh --user user-a
export QFW_SHARED_ROOT=/workspace/qfw-container-base
# Uncomment the line below only if you want to use the QFw installed
# with "./do_qfw_build.sh" rather than the QFw that comes in the
# container image.
#export QFW_PREFIX=$QFW_SHARED_ROOT/qfw-install
source $QFW_INSTALL_PREFIX/bin/qfw-activate --venv $QFW_INSTALL_PREFIX/../qfw-venv
cd $QFW_SHARE_DIR/examples
./qfw_run_all.sh --service-mode site --backend shim --verbose --tests init-test,qiskit-simple,ghz-qiskit
```

The output of a successful run would include messages like below.

```text
[1] init-test: ./qfw_init_test.sh --verbose --service-mode site --backend shim --site-config /etc/openqse/qfw/site.yaml
[1] init-test: PASS (/workspace/home/user-a/qfw-runs/examples-run-20261022-212604-176558681/01-init-test.log)
[2] qiskit-simple: ./qfw_qiskit_simple.sh --verbose --service-mode site --backend shim --site-config /etc/openqse/qfw/site.yaml 4
[2] qiskit-simple: PASS (/workspace/home/user-a/qfw-runs/examples-run-20261022-212604-176558681/02-qiskit-simple.log)
[3] ghz-qiskit: ./qfw_ghz.sh --verbose --service-mode site --backend shim --site-config /etc/openqse/qfw/site.yaml qiskit 4 shim 1
[3] ghz-qiskit: PASS (/workspace/home/user-a/qfw-runs/examples-run-20261022-212604-176558681/03-ghz-qiskit.log)
```

## 3. Other ways to run a circuit in `ibm-fake-lagos`

The examples below don't use salloc or sbatch, so they are not an end-to-end slurm QFw execution. However, they can be useful to quickly test or validate new QFw
changes or installations. In these examples, we run the circuit directly in the
`slurmctld`.

### 3.1 Local QPM

#### Prerequisites

- The `qsa-sim` started and configured. Only the steps 1 and 4 from the [start-ibm-qsa-sim.md](./start-ibm-qsa-sim.md) are required.

#### Running the circuit

```bash
./do_ssh.sh --user user-a
export QFW_SHARED_ROOT=/workspace/qfw-container-base
# Uncomment the line below only if you want to use the QFw installed
# with "./do_qfw_build.sh" rather than the QFw that comes in the
# container image.
#export QFW_PREFIX=$QFW_SHARED_ROOT/qfw-install
source $QFW_INSTALL_PREFIX/bin/qfw-activate --venv $QFW_INSTALL_PREFIX/../qfw-venv
cd $QFW_SHARE_DIR/examples
./qfw_ibm_qpm_local.sh ~/device-access.yaml
```

The output of a successful run would include the messages below at the bottom. It would also include RESULT fields such as `metrics.counts` and circuit parameter values.

```text
QFW_EXAMPLE_RESULT {
  "args": [
    "/workspace/home/user-a/device-access.yaml"
  ],
  "duration_sec": 37.0,
  "event": "finish",
  "example": "qsa-qpm-local",
  "kind": "wrapper",
  "rc": 0,
  "schema": "qfw-example-wrapper-v1",
  "status": "ok",
  "teardown_rc": 0,
  "timestamp_ns": 1792700861396783338
}
```

### 3.2 No QPM, just the Frontend

#### Prerequisites

- The `qsa-sim` is started and configured. Only the steps 1 and 4 from the [start-ibm-qsa-sim.md](./start-ibm-qsa-sim.md) are required.

#### Running the circuit

```bash
./do_ssh.sh --user user-a
export QFW_SHARED_ROOT=/workspace/qfw-container-base
# Uncomment the line below only if you want to use the QFw installed
# with "./do_qfw_build.sh" rather than the QFw that comes in the
# container image.
#export QFW_PREFIX=$QFW_SHARED_ROOT/qfw-install
source $QFW_INSTALL_PREFIX/bin/qfw-activate --venv $QFW_INSTALL_PREFIX/../qfw-venv
cd $QFW_SHARE_DIR/examples
./qfw_ibm_frontend.sh ~/device-access.yaml
```

The output of a successful run would include messages like below at the bottom. It would also include qiskit circuit compilation passes and calls to each qrmi_driver capability.

```text
2026-10-22 20:48:29,522 - qiskit.passmanager.base_tasks - [INFO] - base_tasks.py:execute() -> Pass: Size - 0.00119 (ms)
2026-10-22 20:48:29,522 - qiskit.passmanager.base_tasks - [INFO] - base_tasks.py:execute() -> Pass: FixedPoint - 0.00167 (ms)
2026-10-22 20:48:29,522 - qiskit.passmanager.base_tasks - [INFO] - base_tasks.py:execute() -> Pass: ContainsInstruction - 0.00381 (ms)
2026-10-22 20:48:29,522 - qiskit.passmanager.base_tasks - [INFO] - base_tasks.py:execute() -> Pass: InstructionDurationCheck - 0.00453 (ms)
2026-10-22 20:48:29,545 - root - [INFO] - ibm_transcode.py:qiskit_sampler_input_json() -> Circuit param_values used: {'th[0]': 0.1, 'th[1]': 0.2, 'th[2]': 0.3}
2026-10-22 20:48:29,545 - root - [INFO] - ibm_transcode.py:qiskit_sampler_input_json() -> Circuit: parameter_values.shape=() shots=128
2026-10-22 20:48:31,723 - root - [INFO] - test_ibm_frontend.py:<module>() -> Call get_task_timing
2026-10-22 20:48:31,724 - root - [INFO] - test_ibm_frontend.py:<module>() -> get_task_timing = {'cid': 'my_uuid', 'job_id': '61eed3d4-f9c5-4a40-a758-93e58e4a5126', 'status': 'completed', 'timing': {'submit_seconds': 0.034030162962153554, 'wait_seconds': 2.0107210850110278, 'result_fetch_seconds': 0.006771825952455401, 'total_wall_seconds': 2.0515316569944844}}
2026-10-22 20:48:31,724 - root - [INFO] - test_ibm_frontend.py:<module>() -> Call get_task_metadata
2026-10-22 20:48:31,724 - root - [INFO] - test_ibm_frontend.py:<module>() -> get_task_metadata = {'cid': 'my_uuid', 'job_id': '61eed3d4-f9c5-4a40-a758-93e58e4a5126', 'status': 'completed', 'shots': 128, 'backend': 'ibm'}
[Thu Oct 22 20:48:33 UTC 2026] ./qfw_ibm_frontend.sh done on slurmctld

```