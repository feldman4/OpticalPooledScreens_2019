#!/usr/bin/env bash

# Look for installation instructions in README.md

if [ ! -e venv ]
then
  echo "Creating virtualenv in './venv'"
  python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements.txt
# link ops package instead of copying
# jupyter and snakemake will import code from .py files in the ops/ directory
pip install -e .

