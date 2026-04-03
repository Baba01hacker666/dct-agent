#!/bin/bash
pip install autoflake
autoflake --in-place --remove-all-unused-imports --recursive dct/
