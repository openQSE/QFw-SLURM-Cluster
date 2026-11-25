cwlVersion: v1.2
class: CommandLineTool
baseCommand:
- python3
- stages.py
- collect
requirements:
  InitialWorkDirRequirement:
    listing:
    - entryname: stages.py
      entry:
        $include: stages.py
inputs:
  application:
    type: Directory
    inputBinding:
      prefix: --application
  prepared:
    type: Directory
    inputBinding:
      prefix: --prepared
  calculations:
    type: Directory[]
    inputBinding:
      prefix: --calculations
arguments: []
outputs:
  results:
    type: Directory
    outputBinding:
      glob: results
stdout: stage.out
stderr: stage.err
