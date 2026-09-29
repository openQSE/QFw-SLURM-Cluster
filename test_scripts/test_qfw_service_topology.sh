#!/bin/bash

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
slurm_config="${repo_dir}/slurm.conf"
compose_config="${repo_dir}/docker-compose.yml"
user_profile="${repo_dir}/config/qfw-user-profile.sh"
device_config="${repo_dir}/config/device-access.yaml"
credential_config="${repo_dir}/config/qpu-users.json"
service_config="${repo_dir}/config/site-services.yaml"
resource_config="${repo_dir}/config/qfw-slurm/resources.lua"
plugin_config="${repo_dir}/config/qfw-slurm/plugin.conf"

for node in nwqsim-head nwqsim-worker-1 nwqsim-worker-2 iqm-head shim-head ibm-156-nh aws fake-iqm-head; do
	grep -q "^NodeName=${node} " "${slurm_config}"
	grep -q "^  ${node}:$" "${compose_config}"
done

grep -q '^PartitionName=normal .*Nodes=c\[1-8\]' "${slurm_config}"
grep -q '^PartitionName=qfw-services .*AllowGroups=root' "${slurm_config}"
grep -q '^NodeName=nwqsim-head .*qpm-nwqsim' "${slurm_config}"
grep -q '^NodeName=nwqsim-worker-1 .*qpm-nwqsim' "${slurm_config}"
grep -q '^NodeName=nwqsim-worker-2 .*qpm-nwqsim' "${slurm_config}"
grep -q '^NodeName=iqm-head .*qpm-iqm-ornl-20q' "${slurm_config}"
grep -q '^NodeName=shim-head .*qpm-shim-ornl-20q' "${slurm_config}"
grep -q '^NodeName=ibm-156-nh .*qpm-shim-ibm-156-nh' "${slurm_config}"
grep -q '^NodeName=aws .*qpm-shim-aws-qpm' "${slurm_config}"
grep -A7 '^  aws:$' "${compose_config}" |
	grep -q '^    container_name: aws$'
grep -q '^NodeName=fake-iqm-head .*qpm-fake-iqm' "${slurm_config}"
grep -q '^set root /opt/qfw/openmpi$' "${repo_dir}/modulefiles/openmpi"
grep -q '^export QFW_SIMULATOR_NODES=nwqsim-head,nwqsim-worker-1,nwqsim-worker-2$' \
	"${user_profile}"

if grep '^PartitionName=normal ' "${slurm_config}" |
	grep -Eq 'nwqsim|iqm-head|shim-head|ibm-156-nh|aws|fake-iqm-head'; then
	echo "service node leaked into the normal partition" >&2
	exit 1
fi

grep -q '\["ibm-156-nh"\] = "shim-ibm-156-nh"' "${resource_config}"
grep -A1 '^\[resource "ibm-156-nh"\]$' "${plugin_config}" |
	grep -q '^service_id=shim-ibm-156-nh$'
for resource in aws-ionq-aria-1 aws-rigetti-ankaa; do
	grep -q "\[\"${resource}\"\] = \"shim-aws-qpm\"" "${resource_config}"
	grep -A1 "^\[resource \"${resource}\"\]$" "${plugin_config}" |
		grep -q '^service_id=shim-aws-qpm$'
done
grep -q '/etc/openqse/qfw/services/site-services.yaml:0644' \
	"${repo_dir}/tools/provision-qfw-cluster.sh"
python3 - "${device_config}" "${service_config}" \
	"${credential_config}" "${repo_dir}/config/site.yaml" <<'PY'
import json
import sys

import yaml

with open(sys.argv[1], encoding="utf-8") as stream:
    qpus = yaml.safe_load(stream)["qpus"]
device = qpus["ibm-156-nh"]
assert device["provider"] == "ibm"
assert device["provider-device-id"] == "ibm_156_nh"
assert device["resource-type"] == "IBMQiskitRuntimeService"
assert device["libraries"] == ["qrmi"]
assert device["preference"] == "qrmi"
assert device["execution-owner"] == "qrmi"
assert device["caps"] == {
    "run_circuit": ["qrmi"],
    "get_task_timing": ["qrmi"],
    "get_task_metadata": ["qrmi"],
}

with open(sys.argv[2], encoding="utf-8") as stream:
    services = yaml.safe_load(stream)["services"]
ibm_services = [service for service in services
                if service["name"] == "shim-ibm-156-nh"]
assert len(ibm_services) == 1
assert ibm_services[0]["device-id"] == "ibm-156-nh"
assert ibm_services[0]["module"] == "svc_lib_qpm"

aws_service = [service for service in services
               if service["name"] == "shim-aws-qpm"]
assert len(aws_service) == 1
assert aws_service[0]["device-id"] == "aws"
assert aws_service[0]["module"] == "svc_lib_qpm"

assert qpus["aws"]["libraries"] == ["qdmi"]
assert qpus["aws"]["execution-owner"] == "qdmi"
assert qpus["aws-ionq-aria-1"]["provider-device-id"] == \
    "arn:aws:braket:us-east-1::device/qpu/ionq/Aria-1"
assert qpus["aws-rigetti-ankaa"]["provider-device-id"] == \
    "arn:aws:braket:us-west-1::device/qpu/rigetti/Ankaa-3"

with open(sys.argv[3], encoding="utf-8") as stream:
    users = json.load(stream)["users"]
assert users
for record in users.values():
    credential = record["devices"]["ibm-156-nh"]
    assert credential["enabled"] is True
    assert set(credential) == {"enabled", "api_key", "service_crn"}
    for device_id in ("aws", "aws-ionq-aria-1", "aws-rigetti-ankaa"):
        aws_credential = record["devices"][device_id]
        assert aws_credential["enabled"] is True
        assert set(aws_credential) == {
            "enabled", "api_key", "aws_access_key_id",
            "aws_secret_access_key", "aws_session_token",
        }

with open(sys.argv[4], encoding="utf-8") as stream:
    site = yaml.safe_load(stream)
assert site["service"]["manifest"] == \
    "/etc/openqse/qfw/services/site-services.yaml"
PY

echo "QFw service topology configuration passed"
