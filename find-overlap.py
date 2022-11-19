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
import hashlib
import sys


BLOCKSIZE = 1024*1024


def read_hashes(f):
    """Return list of MD5 hashes for all blocks read from the open file
    object.
    """
    md5_hashes = []
    while True:
        data = f.read(BLOCKSIZE)
        if not data:
            break
        md5_hash = hashlib.md5(data).digest()
        md5_hashes.append(md5_hash)
    return md5_hashes


def generate_matching_hashes(md5_hashes):
    """Return a dictionary with MD5 hash as the key to the list of
    blocks numbers with with the same hash from the list of MD5 hashes.

    Example:

        >>> generate_matching_hashes(['#0', '#0', '#2'])
        {'#0': [0, 1], '#2': [2]}

    Read the returned dictionary as key '#0' is the hash for data blocks
    0 and 1, and key '#2' is the hash for block 2.
    """
    matching_hashes = {}
    blknum = 0
    for md5_hash in md5_hashes:
        if md5_hash in matching_hashes:
            matching_hashes[md5_hash].append(blknum)
        else:
            matching_hashes[md5_hash] = [blknum]
        blknum += 1
    return matching_hashes


def eliminate_non_duplicates(matching_hashes):
    """Mutate the passed matching hashes dictionary deleting items
    (MD5 hash keys and block number lists) of non-duplicate blocks.

    Example:
        >>> matching_hashes = {'#0': [0],
                               '#1': [1, 2],
                               '#2': [3],
                               '#3': [4, 5, 6]}
        >>> eliminate_non_duplicates(matching_hashes)
        >>> matching_hashes
        {'#1': [1, 2]}
    """
    # FIXME:
    # Investigate whether using offsets between groups of three or more
    # blocks with the same MD5 hash adds to the signal or noise.
    for key, value in matching_hashes.items():
        if len(value) != 2:
            del matching_hashes[key]


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
