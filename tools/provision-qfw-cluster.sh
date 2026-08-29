#!/bin/bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
user_file="${script_dir}/config/qfw-users.conf"
profile_file="${script_dir}/config/qfw-user-profile.sh"
site_file="${script_dir}/config/site.yaml"
device_file="${script_dir}/config/device-access.yaml"
credential_file="${script_dir}/config/qpu-users.json"
account="qfw-test"
containers=(slurmdbd slurmctld slurmrestd c1 c2 c3 c4 c5 c6 c7 c8)

die() {
	echo "qfw-provision: $*" >&2
	exit 1
}

for path in "${user_file}" "${profile_file}" "${site_file}" \
		"${device_file}" "${credential_file}"; do
	[[ -r "${path}" ]] || die "required file is not readable: ${path}"
done

awk -F: '
	/^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
	NF != 5 { invalid = 1 }
	END { exit invalid }
' "${user_file}" || die "invalid user definition: ${user_file}"
mapfile -t users < <(
	awk -F: '
		/^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
		{ print }
	' "${user_file}"
)
[[ ${#users[@]} -gt 0 ]] || die "no users are defined in ${user_file}"

for container in "${containers[@]}"; do
	docker inspect "${container}" >/dev/null 2>&1 ||
		die "container is not available: ${container}"

	for definition in "${users[@]}"; do
		IFS=: read -r name uid gid home shell <<<"${definition}"
		[[ "${name}" =~ ^[a-z_][a-z0-9_-]*$ ]] ||
			die "invalid user name: ${name}"
		[[ "${uid}" =~ ^[0-9]+$ && "${gid}" =~ ^[0-9]+$ ]] ||
			die "invalid numeric identity for ${name}"
		[[ "${home}" == /workspace/home/* && "${shell}" == /* ]] ||
			die "invalid home or shell for ${name}"

		docker exec -i "${container}" bash -s -- \
			"${name}" "${uid}" "${gid}" "${home}" "${shell}" <<'EOF'
set -euo pipefail

name="$1"
uid="$2"
gid="$3"
home="$4"
shell="$5"

if group_record="$(getent group "${name}")"; then
	actual_gid="$(cut -d: -f3 <<<"${group_record}")"
	[[ "${actual_gid}" == "${gid}" ]] || {
		echo "group ${name} has GID ${actual_gid}, expected ${gid}" >&2
		exit 1
	}
elif getent group "${gid}" >/dev/null; then
	echo "GID ${gid} is already assigned to another group" >&2
	exit 1
else
	groupadd --gid "${gid}" "${name}"
fi

if passwd_record="$(getent passwd "${name}")"; then
	IFS=: read -r _ _ actual_uid actual_gid _ actual_home actual_shell \
		<<<"${passwd_record}"
	[[ "${actual_uid}:${actual_gid}:${actual_home}:${actual_shell}" == \
	   "${uid}:${gid}:${home}:${shell}" ]] || {
		echo "user ${name} does not match its configured identity" >&2
		exit 1
	}
elif getent passwd "${uid}" >/dev/null; then
	echo "UID ${uid} is already assigned to another user" >&2
	exit 1
else
	useradd --uid "${uid}" --gid "${gid}" --home-dir "${home}" \
		--shell "${shell}" --no-create-home "${name}"
	usermod --lock "${name}"
fi

install -d -o root -g root -m 0755 /workspace/home
install -d -o "${uid}" -g "${gid}" -m 0700 "${home}"
install -d -o "${uid}" -g "${gid}" -m 0700 "${home}/qfw-runs"
EOF
	done

	docker cp "${profile_file}" \
		"${container}:/tmp/qfw-test-user-profile.sh"
	docker exec "${container}" bash -s <<'EOF'
set -euo pipefail
install -o root -g root -m 0644 /tmp/qfw-test-user-profile.sh \
	/etc/profile.d/qfw-test-user.sh
rm -f /tmp/qfw-test-user-profile.sh
EOF

	declare -a files=(
		"${site_file}:/etc/openqse/qfw/site.yaml:0644"
		"${device_file}:/etc/openqse/qfw/device/device-access.yaml:0600"
		"${credential_file}:/etc/openqse/qfw/device/qpu-users.json:0600"
	)
	for specification in "${files[@]}"; do
		IFS=: read -r source destination mode <<<"${specification}"
		temporary="/tmp/qfw-provision-$(basename "${destination}")"
		docker cp "${source}" "${container}:${temporary}"
		docker exec -i "${container}" bash -s -- \
			"${temporary}" "${destination}" "${mode}" <<'EOF'
set -euo pipefail

temporary="$1"
destination="$2"
mode="$3"

install -d -o root -g root -m 0755 /etc/openqse/qfw
install -d -o root -g root -m 0700 /etc/openqse/qfw/device
if [[ ! -e "${destination}" ]]; then
	install -o root -g root -m "${mode}" "${temporary}" "${destination}"
fi
rm -f "${temporary}"
EOF
	done
done

if ! docker exec slurmctld sacctmgr --noheader --parsable2 show account \
		where Name="${account}" format=Account |
	grep -qx "${account}"; then
	docker exec slurmctld sacctmgr --immediate add account "${account}" \
		Description="QFw test users" Organization="openQSE" >/dev/null
fi

for definition in "${users[@]}"; do
	IFS=: read -r name _ _ _ _ <<<"${definition}"
	if ! docker exec slurmctld sacctmgr --noheader --parsable2 \
			show association where User="${name}" Account="${account}" \
			format=User,Account |
		grep -qx "${name}|${account}"; then
		docker exec slurmctld sacctmgr --immediate add user "${name}" \
			Account="${account}" DefaultAccount="${account}" >/dev/null
	fi
	default_account="$(
		docker exec slurmctld sacctmgr --noheader --parsable2 show user \
			where Name="${name}" format=DefaultAccount
	)"
	if [[ "${default_account}" != "${account}" ]]; then
		docker exec slurmctld sacctmgr --immediate modify user \
			where Name="${name}" set DefaultAccount="${account}" >/dev/null
	fi
done

echo "Provisioned ${#users[@]} QFw users in ${#containers[@]} containers."
