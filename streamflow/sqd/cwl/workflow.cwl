cwlVersion: v1.2
class: Workflow
requirements:
  SubworkflowFeatureRequirement: {}
  EnvVarRequirement:
    envDef:
      QFW_SHARED_ROOT: /workspace/qfw-container-base
      OMP_NUM_THREADS: '1'
      OPENBLAS_NUM_THREADS: '1'
      MKL_NUM_THREADS: '1'
inputs:
  fcidump: File
  config: File
  sampler: File
  solver: File
outputs:
  result:
    type: File
    outputSource: iteration/next_state
steps:
  prepare:
    run: tools.cwl#prepare
    in:
      fcidump: fcidump
      config: config
    out:
    - problem
    - state
  iteration:
    run: iteration.cwl
    in:
      problem: prepare/problem
      state: prepare/state
      sampler: sampler
      solver: solver
    out:
    - next_state
