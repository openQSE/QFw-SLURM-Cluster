#!/bin/bash
# do_startup.sh refreshes the Slurm files in the etc_slurm volume that differ
# from the checkout, and tools/provision-qfw-cluster.sh refuses to run while a
# container is not running (#77). Both run here against a docker stand-in, from
# a copy of the checkout's scripts and configuration.

set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temporary="$(mktemp -d)"
trap 'rm -rf "${temporary}"' EXIT

fail() {
	echo "test_startup_slurm_files: $*" >&2
	exit 1
}

cluster="${temporary}/cluster"
state="${temporary}/state"
mkdir -p "${cluster}/tools" "${temporary}/base" "${temporary}/bin" \
	"${state}/containers" "${state}/volume"
cp "${repo_dir}/do_startup.sh" "${repo_dir}/update_slurmfiles.sh" \
	"${repo_dir}/register_cluster.sh" "${cluster}/"
cp "${repo_dir}/slurm.conf" "${repo_dir}/slurmdbd.conf" \
	"${repo_dir}/cgroup.conf" "${repo_dir}/rest.conf" "${repo_dir}/gres.conf" \
	"${cluster}/"
cp "${repo_dir}/tools/compose-env.sh" \
	"${repo_dir}/tools/provision-qfw-cluster.sh" "${cluster}/tools/"
cp -R "${repo_dir}/config" "${cluster}/config"
printf 'QFW_CONTAINER_BASE=%s\n' "${temporary}/base" >"${cluster}/qfw-install.env"

# The stand-in records every call in docker.log, serves /etc/slurm from
# state/volume and container states from state/containers/<name> (no file:
# running; "missing": no such container). A compose restart starts every exited
# slurmd whose NodeName the volume's slurm.conf has by then, as the real one
# does.
cat >"${temporary}/bin/docker" <<'EOF'
#!/bin/bash
set -euo pipefail
state_dir="${FAKE_DOCKER_STATE}"
printf '%s\n' "$*" >>"${state_dir}/docker.log"
case "$1" in
compose)
	if [[ " $* " == *" restart"* ]]; then
		for path in "${state_dir}"/containers/*; do
			[[ -f "${path}" ]] || continue
			name="$(basename "${path}")"
			if [[ "$(cat "${path}")" == exited ]] &&
				grep -q "^NodeName=${name} " "${state_dir}/volume/slurm.conf"; then
				echo running >"${path}"
			fi
		done
	fi
	;;
inspect)
	name="${!#}"
	path="${state_dir}/containers/${name}"
	if [[ -f "${path}" ]]; then
		container_state="$(cat "${path}")"
		if [[ "${container_state}" == missing ]]; then
			echo "Error: No such object: ${name}" >&2
			exit 1
		fi
		echo "${container_state}"
	else
		echo running
	fi
	;;
logs)
	echo "slurmd: fatal: Unable to determine this slurmd's NodeName"
	;;
exec)
	shift
	interactive=false
	if [[ "$1" == -i ]]; then
		interactive=true
		shift
	fi
	shift
	if [[ "${1:-}" == cat && "${2:-}" == /etc/slurm/* ]]; then
		cat "${state_dir}/volume/${2#/etc/slurm/}"
	elif [[ "${1:-}" == sh && "${2:-}" == -c &&
			"${3:-}" == "cat >/etc/slurm/"* ]]; then
		cat >"${state_dir}/volume/${3#cat >/etc/slurm/}"
	elif [[ "$*" == *"list cluster name=linux"* ]]; then
		echo linux
	elif ${interactive}; then
		cat >/dev/null
	fi
	;;
esac
EOF
chmod +x "${temporary}/bin/docker"
export FAKE_DOCKER_STATE="${state}"
export PATH="${temporary}/bin:${PATH}"

# update_slurmfiles.sh copies a file as it is: no expansion of $ or backticks,
# trailing newlines kept, owner and mode of the volume's copy untouched.
printf 'AutoDetect=off\n# $HOME `date` "quoted" \\n\n\n' >"${cluster}/gres.conf"
(cd "${cluster}" && ./update_slurmfiles.sh gres.conf >/dev/null)
cmp -s "${state}/volume/gres.conf" "${cluster}/gres.conf" ||
	fail "update_slurmfiles.sh changed the content of gres.conf"
grep -q '^compose .* restart$' "${state}/docker.log" ||
	fail "update_slurmfiles.sh did not restart the containers"

# The volume predates the Backline node: its slurm.conf has no entry for
# qec-backline-head, so that node's slurmd exited. qsa-sim-head was never
# created. The other files match the checkout.
sed '/^NodeName=qec-backline-head /d' "${cluster}/slurm.conf" \
	>"${state}/volume/slurm.conf"
for file in slurmdbd.conf cgroup.conf rest.conf; do
	cp "${cluster}/${file}" "${state}/volume/${file}"
done
echo exited >"${state}/containers/qec-backline-head"
echo missing >"${state}/containers/qsa-sim-head"

# Provisioning stops before it runs anything, and says what is wrong.
: >"${state}/docker.log"
if (cd "${cluster}" && ./tools/provision-qfw-cluster.sh \
		>"${temporary}/provision.out" 2>"${temporary}/provision.err"); then
	fail "provisioning succeeded although two containers are not running"
fi
grep -q '^qfw-provision: container is not running (exited): qec-backline-head$' \
	"${temporary}/provision.err" ||
	fail "the stopped container was not reported"
grep -q "Unable to determine this slurmd's NodeName" "${temporary}/provision.err" ||
	fail "the stopped container's log was not shown"
grep -q '^qfw-provision: container does not exist: qsa-sim-head$' \
	"${temporary}/provision.err" ||
	fail "the missing container was not reported"
grep -q 'do_startup.sh refreshes the Slurm configuration' "${temporary}/provision.err" ||
	fail "the remedy was not named"
if grep -q '^exec ' "${state}/docker.log"; then
	fail "provisioning ran commands in containers before the check passed"
fi

# do_startup.sh notices that only slurm.conf is stale, refreshes it, restarts
# the containers once, and provisions once the node's slurmd is back.
rm "${state}/containers/qsa-sim-head"
: >"${state}/docker.log"
(cd "${cluster}" && ./do_startup.sh >"${temporary}/startup.out" 2>"${temporary}/startup.err") ||
	fail "do_startup.sh failed on a stale volume: $(tail -5 "${temporary}/startup.err")"
grep -q '^---> Slurm configuration in the etc_slurm volume differs from the checkout: slurm.conf$' \
	"${temporary}/startup.out" ||
	fail "do_startup.sh did not report the stale slurm.conf alone"
cmp -s "${state}/volume/slurm.conf" "${cluster}/slurm.conf" ||
	fail "the volume's slurm.conf was not refreshed"
[[ "$(grep -c '^compose .* restart$' "${state}/docker.log")" -eq 1 ]] ||
	fail "expected exactly one compose restart"
[[ "$(cat "${state}/containers/qec-backline-head")" == running ]] ||
	fail "the restart did not bring qec-backline-head back"
grep -q '^Provisioned ' "${temporary}/startup.out" ||
	fail "provisioning did not run to the end"

# A second start finds nothing stale and restarts nothing.
: >"${state}/docker.log"
(cd "${cluster}" && ./do_startup.sh >"${temporary}/startup2.out" 2>/dev/null) ||
	fail "the second do_startup.sh failed"
if grep -q 'differs from the checkout' "${temporary}/startup2.out"; then
	fail "the second start still saw stale files"
fi
if grep -q ' restart' "${state}/docker.log"; then
	fail "the second start restarted the containers"
fi

(cd "${cluster}" && ./do_startup.sh --dry-run) >"${temporary}/dry-run.out"
grep -q 'refresh the Slurm files in the etc_slurm volume' "${temporary}/dry-run.out" ||
	fail "the dry run does not list the refresh"

echo "test_startup_slurm_files: OK"
