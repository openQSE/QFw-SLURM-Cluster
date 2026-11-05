from pathlib import Path

def setup_FMO(fcidump_path: str):
	base_path = Path(fcidump_path).expanduser().resolve(strict=True)
	pattern_prefix = base_path.name
	monomer_files = sorted(base_path.parent.glob(f"{pattern_prefix}-1-*"))
	dimer_files = sorted(base_path.parent.glob(f"{pattern_prefix}-2-*"))

	if not monomer_files:
		raise ValueError(f"no monomer FCIDUMP files found for {base_path}")
	if not dimer_files:
		raise ValueError(f"no dimer FCIDUMP files found for {base_path}")

	return monomer_files, dimer_files
