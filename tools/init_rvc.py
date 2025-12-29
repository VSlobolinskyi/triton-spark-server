#!/usr/bin/env python3
"""Initialize RVC and print config."""
import sys
import os

# Setup path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)
os.chdir(ROOT_DIR)

from rvc import init_rvc, get_config

init_rvc()
config = get_config()
print(f"RVC initialized:")
print(f"  Device: {config.device}")
print(f"  Half precision: {config.is_half}")
print(f"  GPU: {config.gpu_name}")
