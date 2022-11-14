#!/usr/bin/env python
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2022 Mike Fleetwood
# FILE: find-overlap.py

"""find-overlap.py - Find overlapping portion of data

Command line tool which reads a file system (or any other data) and
identifies the portion duplicated after an interrupted overwriting copy
as performed by GParted when resizing/moving a partition.

Works by computing the MD5 hash of every block and finding blocks with
exactly one duplicate copy to identify the overlap size and location.

Command line usage:
    find-overlap.py [DEVICE]
"""


import argparse
import sys


def main(args=None):
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description="""
        Find overlapping portion of a file system after an interrupted
        GParted resize/move.""")
    parser.add_argument('device', nargs='?', help="""
        optional device or file to read""")
    args = parser.parse_args(args)
    print('device='+repr(args.device))


if __name__ == '__main__':
    sys.exit(main())
