# Want to reproduce VASP calculations from Materials Project

Sometimes, we want to quickly set up a calculation from materials project and then check with the input. It is a quite tedious to do it manually by copying the files from MP and then set up calculations in your own environment. Here is a simple workflow to automate this process.

This folder contains `query.py`, a script to download one Materials Project entry (lowest `energy_above_hull`) for a given formula + lattice type and generate ready-to-run VASP inputs.

## What `query.py` generates
For each run, it creates a folder named:

- `<formula>-<lattice_type>-<mp_id>`

Example:

- `Gd2Co17-hexagonal-mp-1201816`

Inside that folder, it writes:

- `README.md` (mp-id, DFT energy, energy above hull, XC info, POTCAR info)
- `POSCAR`
- `INCAR` (compact MP input INCAR)
- `KPOINTS`
- `POTCAR` (assembled from your local POTCAR library)
- `final_structure.cif`


After downloading the input files, go to the desired folder (e.g, ``Gd2Co17-hexagonal-mp-1201816``)

```
cd Gd2Co17-hexagonal-mp-1201816
sbatch ../job.sh
```

This way, you can easily check if the output energy is consisetent with your results and play with the INCAR/POTCAR/KPOINTS files for a better comparison.


To enable this function, do the followings

## 1) Prerequisites

Activate your Python environment and install dependencies:

```bash
pip install mp-api pymatgen
```

## 2) Modify the slurm script
Modify the `job.sh` file according to your own environment.


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

## 3) Run the script

From the root folder:

```bash
python query.py --formula Gd2Co17 --space-group-type hexagonal
```

Optional explicit POTCAR path (default is already set to your cluster path):

```bash
python query.py \
  --formula Gd2Co17 \
  --space-group-type hexagonal \
  --potcar-root /projects/mmi/potcarFiles/VASP5.2/potpaw_PBE/
```