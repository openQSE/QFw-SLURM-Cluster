cwlVersion: v1.2
class: Workflow
label: He4 fragment calculations through QFw
requirements:
  ScatterFeatureRequirement: {}
  MultipleInputFeatureRequirement: {}
inputs:
  case:
    type:
      type: record
      fields:
        name: string
        gamess_input: File
        fcidump: File
        fragments: File[]
  application: Directory
  settings_a:
    type:
      type: record
      fields:
        qfw:
          type:
            type: record
            fields:
              shared_root: string
              resource: string
              provider: string
              shots: int
              result_kind: string
        optimizer:
          type:
            type: record
            fields:
              macro_iterations: int
              amplitude_iterations: int
              orbital_iterations: int
  settings_b:
    type:
      type: record
      fields:
        qfw:
          type:
            type: record
            fields:
              shared_root: string
              resource: string
              provider: string
              shots: int
              result_kind: string
        optimizer:
          type:
            type: record
            fields:
              macro_iterations: int
              amplitude_iterations: int
              orbital_iterations: int
outputs:
  results:
    type: Directory
    outputSource: collect/results
steps:
  prepare:
    run: prepare.cwl
    in:
      case: case
    out:
    - prepared
    - group_a
    - group_b
  chemistry_a:
    run: chemistry.cwl
    scatter: fragment
    in:
      fragment: prepare/group_a
      application: application
      settings: settings_a
    out:
    - calculation
  chemistry_b:
    run: chemistry.cwl
    scatter: fragment
    in:
      fragment: prepare/group_b
      application: application
      settings: settings_b
    out:
    - calculation
  collect:
    run: collect.cwl
    in:
      application: application
      prepared: prepare/prepared
      calculations:
        source:
        - chemistry_a/calculation
        - chemistry_b/calculation
        linkMerge: merge_flattened
    out:
    - results
