"""Compile a native MQT program and execute it through live QRI."""

from importlib import metadata
from pathlib import Path

import libquantum as lq
from libquantum_plugin_mqt import plugin_path
from mqt.core.mlir import QCProgram


manifest = Path(plugin_path()) / "compiler.json"
assert manifest.is_file(), manifest
program_value = QCProgram.from_openqasm_str(
    'OPENQASM 2.0; include "qelib1.inc"; qreg q[2]; creg c[2]; '
    'h q[0]; cx q[0],q[1]; measure q -> c;'
)
context = lq.initialize(lq.InitConfig(compiler_paths=(str(manifest.parent),)))
primary_error = None
try:
    program = context.import_program(program_value)
    query = context.list_routes(program, explain=True)
    assert len(query.routes) == 1, query.rejected
    route = context.open_route(query.routes[0])
    queue = context.create_completion_queue(route)
    target = context.compiler_target(route)
    compiled = context.compile(route, program)
    repeated = context.compile(route, program)
    assert compiled.target_snapshot is target
    assert repeated.target_snapshot is target
    assert compiled.representation.name == "openqasm"
    assert compiled.representation.version == "2.0"
    print({"compiled_payload": compiled.payload}, flush=True)
    operation_id = context.run(
        route,
        compiled,
        queue,
        lq.ExecutionOptions(shots=256),
    )
    status = context.status(operation_id)
    assert isinstance(status, dict) and status.get("cid") == operation_id
    assert queue.wait(300.0)
    completions = queue.get()
    assert len(completions) == 1
    completion = completions[0]
    assert completion.op_id == operation_id
    print({
        "completion_error": repr(completion.error),
        "completion_result": completion.result,
    }, flush=True)
    assert completion.error is None
    counts = completion.result
    assert isinstance(counts, dict), counts
    assert sum(counts.values()) == 256, counts
    assert set(counts).issubset({"00", "11"}), counts
    print({
        "evidence": "simulator",
        "libquantum": metadata.version("libquantum"),
        "mqt_core": metadata.version("mqt-core"),
        "mqt_plugin": metadata.version("libquantum-plugin-mqt"),
        "qiskit": metadata.version("qiskit"),
        "manifest": str(manifest),
        "route_id": route.definition.route_id,
        "route_instance": route.instance_id,
        "operation_id": operation_id,
        "layout": str(compiled.layout),
        "parameter_metadata": dict(compiled.parameter_metadata),
        "provenance": str(compiled.provenance),
        "counts": counts,
        "target_reused": True,
    }, flush=True)
    queue.close()
except Exception as error:
    primary_error = error
    print({
        "primary_error": repr(error),
        "primary_cause": repr(getattr(error, "_private_cause", None)),
    }, flush=True)
    raise
finally:
    try:
        result = lq.finalize(context, timeout=300.0)
        assert result.status is lq.FinalizeStatus.FINALIZED, result
    except Exception as error:
        print({
            "finalization_error": repr(error),
            "finalization_cause": repr(
                getattr(error, "_private_cause", None)),
        }, flush=True)
        if primary_error is None:
            raise
print("LIBQUANTUM MQT QRI SYSTEM TEST: PASS")
