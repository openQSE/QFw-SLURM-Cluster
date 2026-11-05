# chemistry_he

The pUCCD solver and the He4 fragment FCIDUMPs, copied unchanged from
[openQSE/chemistry_he](https://github.com/openQSE/chemistry_he) at commit
`afcd8f7cda176114c4ce6db2cd9f92d79bc2d9a0`, so that the example runs with no
other checkout.

| File | Role |
| --- | --- |
| `puccd.py` | The pUCCD ansatz and orbital-optimised VQE |
| `setup_FMO.py` | Finds the monomer and dimer files next to an FCIDUMP |
| `He4/He1-4.FCIDUMP` | The full GAMESS FCIDUMP |
| `He4/He1-4.FCIDUMP-1-*`, `-2-*` | The four monomers and six dimers |

To refresh it, copy these files again from chemistry_he and update the commit
above. Changes to the solver belong in chemistry_he.
