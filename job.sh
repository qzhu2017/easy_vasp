#!/bin/bash
#SBATCH --job-name=Test
#SBATCH --partition=Apus,Orion,Nebula
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=32
#SBATCH --mem=32G
#SBATCH --time=02:00:00

# Load modules
module load vasp/6.4.3

# VASP executable (use srun for SLURM-native MPI launching)
mpirun -np {ncpu} vasp_std