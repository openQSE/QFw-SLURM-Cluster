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
  settings_monomers:
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
  settings_dimers:
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
    - monomers
    - dimers
  monomers:
    run: chemistry.cwl
    scatter: fragment
    in:
      fragment: prepare/monomers
      application: application
      settings: settings_monomers
    out:
    - calculation
  dimers:
    run: chemistry.cwl
    scatter: fragment
    in:
      fragment: prepare/dimers
      application: application
      settings: settings_dimers
    out:
    - calculation
  collect:
    run: collect.cwl
    in:
      application: application
      prepared: prepare/prepared
      calculations:
        source:
        - monomers/calculation
        - dimers/calculation
        linkMerge: merge_flattened
    out:
    - results
