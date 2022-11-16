# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2022 Mike Fleetwood
# FILE: test_command_line.py

"""test_find_overlap.py

Performs find-overlap.py command line parsing tests.

Executes the command with different arguments to perform this testing,
therefore requires the PATH environment variable to be modified so that
'find-overlap.py' is found.  This script adds the current directory to
the start of the PATH so run Pytest like this:

    cd .../find-overlap
    python -m pytest
"""


import os
import subprocess


EXIT_SUCCESS = 0


def setup_module():
    """Extend PATH with current working directory to allow
    find-overlap.py executable to be found
    """
    cwd = os.getcwd()
    path = os.environ['PATH']
    os.environ['PATH'] = cwd + os.pathsep + path


def test_command_line_help_option():
    """Test successful exit status and output includes 'help'"""
    out = subprocess.check_output(['find-overlap.py', '--help'])
    assert 'help' in out


def test_command_line_no_argument():
    rc = subprocess.call(['find-overlap.py'])
    assert rc == EXIT_SUCCESS


def test_command_line_one_argument():
    rc = subprocess.call(['find-overlap.py', '/dev/null'])
    assert rc == EXIT_SUCCESS


def test_command_line_two_arguments():
    rc = subprocess.call(['find-overlap.py', '/dev/null', '/dev/null'])
    assert rc != EXIT_SUCCESS
