cwlVersion: v1.2
class: CommandLineTool
baseCommand:
- python3
- stages.py
- prepare
requirements:
  InitialWorkDirRequirement:
    listing:
    - entryname: stages.py
      entry:
        $include: stages.py
inputs:
  case:
    type:
      type: record
      fields:
        name: string
        gamess_input: File
        fcidump: File
        fragments: File[]
arguments:
- prefix: --case-name
  valueFrom: $(inputs.case.name)
- prefix: --gamess-input
  valueFrom: $(inputs.case.gamess_input.path)
- prefix: --fcidump
  valueFrom: $(inputs.case.fcidump.path)
- prefix: --fragments
  valueFrom: $(inputs.case.fragments)
outputs:
  prepared:
    type: Directory
    outputBinding:
      glob: prepared
  group_a:
    type: File[]
    outputBinding:
      glob: prepared/a/*
  group_b:
    type: File[]
    outputBinding:
      glob: prepared/b/*
stdout: stage.out
stderr: stage.err
