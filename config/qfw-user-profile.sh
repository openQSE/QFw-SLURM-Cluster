# QFw test-user defaults. Installed by tools/provision-qfw-cluster.sh.
case "$(id -un 2>/dev/null)" in
	user-a|user-b|user-c) ;;
	*) return 0 2>/dev/null || exit 0 ;;
esac

export QFW_INSTALL_PREFIX=/opt/openqse/qfw
export QFW_VENV=/opt/openqse/qfw-venv
export QFW_SHARED_ROOT=/workspace/qfw-container-base
export QFW_RUN_BASE_DIR="${HOME}/qfw-runs"
export QFW_SITE_CONFIG=/etc/openqse/qfw/site.yaml
export QFW_SIMULATOR_NODES=nwqsim-head,nwqsim-worker-1,nwqsim-worker-2
