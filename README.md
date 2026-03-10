# Want to reproduce VASP calculations from Materials Project

Sometimes we want to quickly set up a calculation from Materials Project and compare with local runs. Doing this manually is tedious, so this folder provides a simple automated workflow.

This folder contains `query.py`, a script that downloads one Materials Project entry (lowest `energy_above_hull`) for a given formula + space-group type, then prepares ready-to-run VASP inputs.

## What `query.py` generates
For each run, it creates a folder named:

- `<formula>-<space_group>-<mp_id>-<xc_func>`

Examples:

- `Gd2Co17-hexagonal-mp-1201816-Scan`
- `Si-cubic-mp-149-PBE`

Inside that folder, it writes:

- `README.md` (mp-id, energies, XC info, POTCAR info, KSPACING status)
- `POSCAR`
- `INCAR` (compact MP input INCAR)
- `KPOINTS` (only when `KSPACING` is not present in INCAR)
- `POTCAR` (assembled from your local POTCAR library)
- `final_structure.cif`

After downloading the input files, go to the desired folder (e.g. `Gd2Co17-hexagonal-mp-1201816-Scan`):

```bash
cd Gd2Co17-hexagonal-mp-1201816-Scan
sbatch ../job.sh
```

This way, you can check whether local output energies are consistent and then tune INCAR/POTCAR/KPOINTS settings if needed.

## 1) Prerequisites

Activate your Python environment and install dependencies:

```bash
pip install mp-api pymatgen
```

## 2) Modify the Slurm script

Modify `job.sh` according to your environment.

## 3) Set up your Materials Project API key

Add this line to `~/.bashrc`:

```bash
export MP_API_KEY="your_mp_api_key_here"
```

Then reload:

```bash
source ~/.bashrc
```

Check:

```bash
echo $MP_API_KEY
```

## 4) Run the script

From the root folder:

```bash
python query.py --formula Gd2Co17 --space-group-type hexagonal --xc scan
```

Optional explicit POTCAR path (default is already set to your cluster path):

```bash
python query.py \
  --formula Gd2Co17 \
  --space-group-type hexagonal \
  --xc scan \
  --potcar-root /projects/mmi/potcarFiles/VASP5.2/potpaw_PBE/
```

## CLI options

- `--formula`, `-f`: chemical formula (e.g., `Si`, `Gd2Co17`)
- `--space-group-type`, `-s`: crystal system filter (e.g., `cubic`, `hexagonal`)
- `--xc`: target XC family: `auto` (default), `gga`, or `scan`
- `--potcar-root`: local POTCAR root path
- `--api-key`: MP API key (defaults to `MP_API_KEY` env var)

If no task matches the requested XC family (`--xc gga` or `--xc scan`), the script exits with a clear error.

## Notes

- Generated per-material README includes: mp-id, DFT-energy (eV/atom), total-energy (eV/cell), energy above hull, XC functional, and POTCAR info.
- Total energy is computed as: `DFT-energy (eV/atom) * nsites`.
- If `KSPACING` is present in INCAR, `KPOINTS` is intentionally not written.
