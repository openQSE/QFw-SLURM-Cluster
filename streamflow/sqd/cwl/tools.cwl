cwlVersion: v1.2
$graph:
- id: prepare
  class: CommandLineTool
  baseCommand:
  - /workspace/qfw-container-base/streamflow-sqd/application/bin/python
  - sqd.py
  - prepare
  requirements:
    InitialWorkDirRequirement:
      listing:
      - entryname: sqd.py
        entry:
          $include: ../sqd.py
  inputs:
    fcidump:
      type: File
      inputBinding:
        prefix: --fcidump
    config:
      type: File
      inputBinding:
        prefix: --config
  outputs:
    problem: Directory
    state: File
  stdout: stage.out
  stderr: stage.err
- id: propose
  class: CommandLineTool
  baseCommand:
  - /workspace/qfw-container-base/streamflow-sqd/application/bin/python
  - sqd.py
  - propose
  requirements:
    InitialWorkDirRequirement:
      listing:
      - entryname: sqd.py
        entry:
          $include: ../sqd.py
  inputs:
    problem:
      type: Directory
      inputBinding:
        prefix: --problem
    state:
      type: File
      inputBinding:
        prefix: --state
  outputs:
    requests: Directory[]
  stdout: stage.out
  stderr: stage.err
- id: sample
  class: CommandLineTool
  baseCommand:
  - /workspace/qfw-container-base/streamflow-sqd/application/bin/python
  - sqd.py
  - sample
  requirements:
    InitialWorkDirRequirement:
      listing:
      - entryname: sqd.py
        entry:
          $include: ../sqd.py
      - class: File
        location: ../sample.sh
  inputs:
    request:
      type: Directory
      inputBinding:
        prefix: --request
    sampler:
      type: File
      inputBinding:
        prefix: --sampler
  outputs:
    samples: Directory
  stdout: stage.out
  stderr: stage.err
- id: solve
  class: CommandLineTool
  baseCommand:
  - /workspace/qfw-container-base/streamflow-sqd/application/bin/python
  - sqd.py
  - solve
  requirements:
    InitialWorkDirRequirement:
      listing:
      - entryname: sqd.py
        entry:
          $include: ../sqd.py
  inputs:
    problem:
      type: Directory
      inputBinding:
        prefix: --problem
    samples:
      type: Directory
      inputBinding:
        prefix: --samples
    solver:
      type: File
      inputBinding:
        prefix: --solver
  outputs:
    results: Directory
  stdout: stage.out
  stderr: stage.err
- id: select
  class: CommandLineTool
  baseCommand:
  - /workspace/qfw-container-base/streamflow-sqd/application/bin/python
  - sqd.py
  - select
  requirements:
    InitialWorkDirRequirement:
      listing:
      - entryname: sqd.py
        entry:
          $include: ../sqd.py
  inputs:
    state:
      type: File
      inputBinding:
        prefix: --state
    results:
      type: Directory[]
      inputBinding:
        prefix: --results
  outputs:
    next_state: File
  stdout: stage.out
  stderr: stage.err
