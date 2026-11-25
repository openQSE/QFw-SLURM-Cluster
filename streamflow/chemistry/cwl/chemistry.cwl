cwlVersion: v1.2
class: CommandLineTool
baseCommand:
- python3
- stages.py
- chemistry
requirements:
  InitialWorkDirRequirement:
    listing:
    - entryname: stages.py
      entry:
        $include: stages.py
    - entryname: fragment.py
      entry:
        $include: fragment.py
    - class: File
      location: fragment.sh
  EnvVarRequirement:
    envDef:
      QFW_SHARED_ROOT: $(inputs.settings.qfw.shared_root)
inputs:
  settings:
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
  application:
    type: Directory
    inputBinding:
      prefix: --application
  fragment:
    type: File
    inputBinding:
      prefix: --fragment
arguments:
- prefix: --backend
  valueFrom: $(inputs.settings.qfw.provider)
- prefix: --qpu
  valueFrom: $(inputs.settings.qfw.resource)
- prefix: --shots
  valueFrom: $(inputs.settings.qfw.shots)
- prefix: --result-kind
  valueFrom: $(inputs.settings.qfw.result_kind)
- prefix: --max-macro-iterations
  valueFrom: $(inputs.settings.optimizer.macro_iterations)
- prefix: --max-amplitude-iterations
  valueFrom: $(inputs.settings.optimizer.amplitude_iterations)
- prefix: --max-orbital-iterations
  valueFrom: $(inputs.settings.optimizer.orbital_iterations)
outputs:
  calculation:
    type: Directory
    outputBinding:
      glob: chemistry
stdout: stage.out
stderr: stage.err
