## Configure and start the IBM QSA simulator in the QFw slurm cluster

This recipe shows how to configure and start the IBM QSA simulator for the
purpose of developement/testing in QFw - please check the
[qsa-sim](https://github.com/qrmi-community/simulated_quantum_resource.git)
repository for further detais and limitations.

If you want to experiment with real IBM Quantum System devices (on-prem), please
check the [IBM Quantum
Plans](https://quantum.cloud.ibm.com/docs/en/guides/plans-overview). 

### 1. Start the `qsa-sim`

Prerequisites:
- docker or podman
- docker-compose or podman-compose
- If using podman, please also install the podman-docker package.

The IBM QSA simulator (qsa-sim) does not need to run within the cluster. You can
install it in the docker host or somewhere else accessible by the cluster.

The instructions below will install and setup the QSA simulator and a
S3-compatible service. For more information, please refer to the
[simulated_quantum_resource](https://github.com/qrmi-community/simulated_quantum_resource)
documentation.

Set the `.env` variables as you see fit. For testing, you could keep them as-is.

```bash
git clone https://github.com/qrmi-community/simulated_quantum_resource.git
cd simulated_quantum_resource
# Update the variables below as necessary
cat << EOF > .env
QSASIM_IAM_APIKEY=myapikey
QSASIM_SERVICE_CRN=myinstance
QSASIM_BIND_PORT=8292
PYTHONUNBUFFERED=1
S3_ACCESS_KEY=myaccesskey
S3_SECRET_KEY=mysecretkey
S3_BUCKET_NAME=mybucket
S3_PORT=9000
S3_CONSOLE_PORT=9001
S3_REGION=us-east
EOF
docker compose up --build
# or: podman compose up --build
```

### 2. Populate credentials in qsa-sim-head

Prerequisites:
- Make sure the cluster was deployed with `--qsa-sim` support - i.e. the
  `qsa-sim-head` container is running. If necessary, redeploy the cluster using
  the commands below.
  ```bash
  ./do_configure.sh --qsa-sim
  ./do_build.sh
  ./do_startup.sh
  ```

Before submiting jobs to `ibm-fake-lagos`, update the `qsa-users.json` and the
`device-access.yaml` in the `qsa-sim-head` container as below. Make sure the
`ibm-fake-lagos` fields are populated with the same values you used to start the
`qsa-sim`. See examples below.

```bash
./do_ssh.sh qsa-sim-head
```

`/etc/openqse/qfw/device/qpu-users.json` example. Populate it for all users.
```json
        "ibm-fake-lagos": {
          "enabled": true,
          "api_key": "myapikey",
          "aws_access_key_id": "myaccesskey",
          "aws_secret_access_key": "mysecretkey"
        }
```

`/etc/openqse/qfw/device/device-access.yaml` example. Make sure you replace the
IP addresses by the IP address of the host where you started the qsa-sim.

```yaml
  ibm-fake-lagos:
    provider: ibm
    resource-type: IBMQuantumSystem
    provider-device-id: fake_lagos
    url: http://192.168.1.41:8292
    iam-endpoint: http://192.168.1.41:8292
    service-crn: "myinstance"
    s3-endpoint: http://192.168.1.41:9000
    s3-bucket: "mybucket"
    s3-region: "us-east"
    job-timeout-seconds: "400"
    credential-db: qpu-users.json
    libraries:
      - qrmi
    preference: qrmi
    execution-owner: qrmi
    caps:
      get_device_info: [qrmi]
      get_coupling_graph: [qrmi]
      get_backend_info: [qrmi]
      get_dynamic_backend_info: [qrmi]
      run_circuit: [qrmi]
      get_task_timing: [qrmi]
      get_task_metadata: [qrmi]
      get_calibration_snapshot: [qrmi]
```

### 3. Start qfw-site-services for qsa-sim

```bash
./do_ssh.sh

qfw-site-services start --target directory
qfw-site-services start --target gateway
qfw-site-services start --target qsa-sim

# Make sure all three services are UP
qfw-site-services status
```

### 4. [Optional] Populate credentials in slurmctld

When the QPM instance is started and managed by the user, the `device-access.yaml` and `qpu-users.json` files must be created in a place where the user can update them, but not accessible by others.

Let's use `user-a` and create the files in the `$HOME`. Similar to the section 2, make sure you populate the files with the values you used to start the qsa-sim - that includes updating the IP addresss as well.

```bash
./do_ssh.sh --user user-a
# Create the qpu-users.json
cat << EOF > ~/qpu-users.json
{
  "users": {
    "user-a": {
      "enabled": true,
      "devices": {
        "ibm-fake-lagos": {
          "enabled": true,
          "api_key": "myapikey",
          "aws_access_key_id": "myaccesskey",
          "aws_secret_access_key": "mysecretkey"
        }
      }
    }
  }
}
EOF
# Create the device-access.yaml pointing to qpu-users.json
cat << EOF > ~/device-access.yaml
qpus:
  ibm-fake-lagos:
    provider: ibm
    resource-type: IBMQuantumSystem
    provider-device-id: fake_lagos
    url: http://192.168.1.41:8292
    iam-endpoint: http://192.168.1.41:8292
    service-crn: "myinstance"
    s3-endpoint: "http://192.168.1.41:9000"
    s3-bucket: "mybucket"
    s3-region: "us-east"
    job-timeout-seconds: "400"
    credential-db: /workspace/home/user-a/qpu-users.json
    libraries: [qrmi]
    preference: qrmi
    execution-owner: qrmi
    caps:
      get_device_info: [qrmi]
      get_coupling_graph: [qrmi]
      get_backend_info: [qrmi]
      get_dynamic_backend_info: [qrmi]
      run_circuit: [qrmi]
      get_task_timing: [qrmi]
      get_task_metadata: [qrmi]
      get_calibration_snapshot: [qrmi]
EOF
```