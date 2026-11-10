cwlVersion: v1.2
class: Workflow
requirements:
  ScatterFeatureRequirement: {}
inputs:
  problem: Directory
  state: File
  sampler: File
  solver: File
outputs:
  next_state:
    type: File
    outputSource: select/next_state
steps:
  propose:
    run: tools.cwl#propose
    in:
      problem: problem
      state: state
    out:
    - requests
  sample:
    run: tools.cwl#sample
    scatter: request
    in:
      request: propose/requests
      sampler: sampler
    out:
    - samples
  solve:
    run: tools.cwl#solve
    scatter: samples
    in:
      problem: problem
      samples: sample/samples
      solver: solver
    out:
    - results
  select:
    run: tools.cwl#select
    in:
      state: state
      results: solve/results
    out:
    - next_state
