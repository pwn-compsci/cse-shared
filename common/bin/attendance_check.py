#!/usr/bin/env python3

import os
import runpy
import sys


script_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
impl = os.path.join(script_dir, "attendance_check.py")

if not os.path.exists(impl):
    sys.stderr.write("attendance_check.py implementation is not available\n")
    sys.exit(1)

runpy.run_path(impl, run_name="__main__")
