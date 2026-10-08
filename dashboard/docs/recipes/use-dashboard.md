# Use the Cluster Dashboard

Start the service and open its reported URL:

```bash
cd /path/to/QFw-SLURM-Cluster
source dashboard/run/environment
qfw-dashboard-service start
qfw-dashboard status
```

The Dashboard pane shows fixed health, node, service, allocation, experiment,
topology, result, and alert widgets. When the optional telemetry stack is up
(see `telemetry/README.md` in the repository root), the health widget links
to its Grafana, where QFw's own job metrics and traces live. Collapse a widget to reduce its footprint
or select **Pop out** to mirror it in another browser window. The original
widget remains in place.

Choose `user-a`, `user-b`, or `user-c` before submitting ordinary experiments.
The selected identity owns the Slurm job and its files. Choose `root` only for
cluster lifecycle, service lifecycle, node recovery, or a root shell. An
identity change applies only to newly submitted work.

Split the workspace to place Progress, File, or Shell beside Dashboard. Use
Progress filters in component-first order. File browses this checkout through
ElectroBoy's Markdown capability. **Open selected cluster shell** starts the
Shell pane in `slurmctld` as the identity selected when the shell was created.
Regular users may also select a compute node allocated to one of their running
jobs. Service-node shells require `root` and a second confirmation.

Cluster Control, Service Control, and Node Control are independent widgets
positioned together on the dashboard canvas. Each widget provides an operation
selector, **Run** and **Abort** controls, and its own live output. Service
Control selects `All services`, `Directory`, `NWQSim`, `IQM`, or `Gateway`;
every request is routed through `qfw-site-services`. Cluster Access is a
separate widget for opening shells. Each control widget can be collapsed or
popped out without changing the others. Select `root` before running or
aborting an administrative operation. Run `man 8 qfw-site-services` for
service target and dependency details.

The experiment form discovers the installed QFw examples. Select normal or
heterogeneous placement, then provide the Slurm partition, node and task counts,
optional account or QoS, and the quantum request bounds. Heterogeneous jobs put
the application and quantum request in group 0, preserving QFw's placement
convention. The persistent site QPMd and DVM remain outside the allocation, so
group 1 does not start local services. **Preview
allocation** shows the exact `sbatch` request. The submitted batch job activates
QFw, runs the example against the persistent site QPM, and deactivates QFw
before Slurm and qfw-slurm release the allocation.

Use the Progress pane's Logs mode to follow application output or an operational
source. Component, context, severity, time, and text filters apply locally.
Operational service logs require `root`; application output remains bound to
the identity that submitted the experiment.

Completed experiments can be retried without modifying the original record.
The Result summary can compare two runs with the same backend and example.
Missing QFw terminal records remain failures even when Slurm reports a zero
exit status.

Real IQM submissions require a separate confirmation and bounded shot count.
Credentials never appear in dashboard forms, retained events, or results.

Run `man qfw-dashboard` for CLI status and diagnostics commands.
