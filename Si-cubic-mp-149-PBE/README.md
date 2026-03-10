# Cubic Si (Materials Project)

## Key metadata
- mp-id: mp-149
- formula: Si
- space-group type: cubic
- DFT-energy (eV/atom): -8.773764595
- total-energy (eV/cell): -17.54752919
- energy_above_hull (eV/atom): 0.0
- xc-functional: PBE (inferred from POTCAR titel)
- KSPACING: N/A

## POTCAR info
```json
[
  {
    "titel": "PAW_PBE Si 05Jan2001",
    "hash": "b2b0ea6feb62e7cde209616683b8f7f5"
  }
]
```

## Notes
- `DFT-energy` is taken from `uncorrected_energy_per_atom` when available; otherwise `energy_per_atom`.
- `total-energy` is computed as `DFT-energy (eV/atom) * nsites`.
- Values are fetched directly from the MP API at runtime.
- `KPOINTS` file written: True

