#!/usr/bin/env python3
"""Headless-browser smoke test for the installed cluster workflow."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from electroboy.service import create_server
from electroboy.service.workflow_config import (
    WorkflowConfig,
    WorkflowFactoryReference,
    save_workflow_config,
)


def main() -> int:
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        print("SKIP: Chrome is not installed")
        return 77
    with tempfile.TemporaryDirectory(prefix="qfw-dashboard-browser-") as temporary:
        root = Path(temporary)
        save_workflow_config(
            root,
            WorkflowConfig(
                enabled_builtins=(),
                extra_workflows=(WorkflowFactoryReference(
                    "qfw-slurm-cluster", "entry-point:qfw-slurm-cluster"
                ),),
            ),
        )
        server = create_server(root, port=0, state_root=root)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            completed = subprocess.run(
                (
                    chrome,
                    "--headless=new",
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    f"--user-data-dir={root / 'chrome-profile'}",
                    "--virtual-time-budget=5000",
                    "--dump-dom",
                    f"http://127.0.0.1:{server.server_address[1]}/",
                ),
                text=True,
                capture_output=True,
                timeout=30,
                check=False,
            )
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()
        if completed.returncode:
            print(completed.stdout)
            print(completed.stderr)
            return completed.returncode
        html = completed.stdout
        required = (
            ">QFw Slurm Cluster</option>",
            ">Dashboard</option>",
            ">AI Agent</option>",
            ">Progress</option>",
            ">File</option>",
            ">Shell</option>",
            'class="shell qfw-slurm-cluster-workflow side-sheet-collapsed"',
            'class="qfw-canvas-viewport"',
            'class="qfw-widget-chevron"',
            ">Cluster control<",
            ">Service control<",
            ">Node control<",
            ">Cluster access<",
            ">Submission Set<",
            ">Add to Submission Set<",
            ">Submit All (0)<",
            '<option value="ibm">IBM</option>',
            '<option value="aws">AWS</option>',
            '<option value="aws-ionq-aria-1">AWS IonQ Aria-1</option>',
            '<option value="aws-rigetti-ankaa">AWS Rigetti Ankaa-3</option>',
        )
        missing = [value for value in required if value not in html]
        forbidden = (
            ">Software Engineering</option>",
            ">Creative Writing</option>",
            ">Agent</option>",
            ">Scratch</option>",
        )
        present = [value for value in forbidden if value in html]
        widgets = tuple(
            f'data-widget="{name}"' for name in (
                "health", "inventory", "cluster-control", "service-control",
                "node-control", "cluster-access", "nodes", "services", "allocations",
                "experiments", "topology", "results", "alerts",
            )
        )
        missing_widgets = [value for value in widgets if value not in html]
        if missing or present or missing_widgets:
            print(f"missing: {missing}")
            print(f"unexpected: {present}")
            print(f"missing widgets: {missing_widgets}")
            return 1
        print("PASS: five-pane workflow and fixed dashboard widgets rendered")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
