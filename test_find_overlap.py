# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2022 Mike Fleetwood
# FILE: test_command_line.py

"""test_find_overlap.py

find-overlap.py command line argument parsing is tested by running this
as an executable so therefore requires the PATH environment variable to
be modified so that it can be found.  This script adds the current
directory to the start of the PATH to enable this, therefore run Pytest
like this:

    cd .../find-overlap
    python -m pytest
"""


import importlib
import io
import os
import subprocess


EXIT_SUCCESS = 0


find_overlap = None


def setup_module():
    """Extend PATH with current working directory to allow
    find-overlap.py executable to be found.  Manually import
    find-overlap module to avoid normal import failing because dash is
    not a valid character in a python identifier.
    """
    cwd = os.getcwd()
    path = os.environ['PATH']
    os.environ['PATH'] = cwd + os.pathsep + path
    global find_overlap
    if not find_overlap:
        find_overlap = importlib.import_module('find-overlap')


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


RESULT_MD5_HASHES = [b"\xb6\xd8\x1b6\nVr\xd8\x0c'C\x0f9\x15>,",
                     b"\xb6\xd8\x1b6\nVr\xd8\x0c'C\x0f9\x15>,",
                     b'Y\x07\x15\x90\t\x9d!\xddC\x98\x96Y#8\xbf\x95']
def test_read_hashes():
    """Test reading 2.5 MiB of binary zero produces the expected list of
    MD5 hashes
    """
    f = io.BytesIO(int(find_overlap.BLOCKSIZE * 2.5) * b'\x00')
    result = find_overlap.read_hashes(f)
    assert result == RESULT_MD5_HASHES


def test_generate_matching_hashes():
    """Test using result from test_read_hashes()"""
    result = find_overlap.generate_matching_hashes(RESULT_MD5_HASHES)
    assert result == {b"\xb6\xd8\x1b6\nVr\xd8\x0c'C\x0f9\x15>,": [0, 1],
                      b'Y\x07\x15\x90\t\x9d!\xddC\x98\x96Y#8\xbf\x95': [2]}


def test_eliminate_non_duplicates():
    test_dict = {'#0': [0], '#1': [1, 2], '#2': [3], '#3': [4, 5, 6]}
    result_dict = {'#1': [1, 2]}
    find_overlap.eliminate_non_duplicates(test_dict)
    assert test_dict == result_dict
