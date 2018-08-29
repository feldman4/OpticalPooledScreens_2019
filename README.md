## Optical Pooled Screens

This repository contains example _in situ_ sequencing-by-synthesis data (in `example_data/`) and analysis code (in `ops/`) for the manuscript *Pooled optical screens in human cells*, which is available on [Biorxiv](https://www.biorxiv.org/content/early/2018/08/02/383943).


### Installation (OSX and popular linux)

Download the OpticalPooledScreens code (e.g., on Github use the green "Clone or download" button, then "Download ZIP") and extract to a local directory.

In `Terminal`, go to the OpticalPooledScreens project directory (e.g. `cd Downloads/opticalpooledscreens-master`) and run:
```bash
sh install.sh
```
This creates a virtual environment called `venv` for project-specific resources (if one does not already exsist) and installs the required packages into the virtual environment.

*Note*: The `ops` package is installed with `pip install -e`, so the source code can be modified from the `ops/` directory without re-installing. The `ops` package is compatible with Python 2.7 as well as Python 3.6, however the results will not be numerically identical.

## Running example code

Once installed, activate the virtual environment from the project directory:

```bash
source venv/bin/activate
```

You can then launch a project-specific notebook server:


```bash
jupyter notebook
```

The notebook `ops_python.ipynb` demonstrates step-by-step analysis using the high-level functions in `ops.firesnake.Snake`. The analysis pipeline can also be run using [snakemake](https://snakemake.readthedocs.io/en/stable/) (after activating the virtual environment):


```bash
cd example_data
snakemake -s Snakefile_20180707_201
```
