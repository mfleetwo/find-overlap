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
    (MD5 hash keys and block number lists) of unique blocks and blocks
    with more than 4 copies, as neither contribute to finding the
    overlapping range.

    Example:
        >>> matching_hashes = {'#0': [0],
                               '#1': [1, 2],
                               '#2': [3],
                               '#3': [4, 5, 6],
                               '#4': [7, 8, 9, 10],
                               '#5': [11, 12, 13, 14, 15]}
        >>> eliminate_non_duplicates(matching_hashes)
        >>> matching_hashes
        {'#1': [1, 2], '#3': [4, 5, 6], '#4': [7, 8, 9, 10]}
    """
    # Real case test-hashes-f18089.txt.xz had:
    #     Blocks:         748453   (1 MiB each)
    #     Overlap size:    19585
    #                                     within overlap range
    #     Unique blocks:         253290
    #     Matching pairs:        19756    19585 ( 99.1%)
    #     Matching triples:      6        0     (  0.0%)
    #     Matching quadruples:   0
    #     
    # Test case test-hashes-t1.txt.xz had:
    # (Ext4 FS with 2 copies of 4.8 GiB of files and partial overlapping
    # copy performed)
    #     Blocks:         20480   (1 MiB each)
    #     Overlap size:    4096
    #                                   within overlap range
    #     Unique blocks:         76
    #     Matching pairs:        1043   1043 (100.0%)
    #     Matching triples:      3665   3665 (100.0%)
    #     Matching quadruples:   0
    #     
    # Therefore keep matching blocks up to a count of 4 replicas to
    # allow for file systems containing multiple copies of files covered
    # by the overlapping range.
    for key, value in matching_hashes.items():
        if len(value) < 2 or len(value) > 4:
            del matching_hashes[key]


def compute_offset_blocks(matching_hashes):
    """Return a new dictionary keyed by the offset between two blocks
    with the same MD5 hash which looks up the list of the first of each
    pair of matched blocks.  The second matching block is simply the
    first block number plus the offset used as the dictionary key.

    Example:
        >>> compute_offset_blocks({'#0': [1, 8],
                                   '#1': [10, 13],
                                   '#2': [11, 14],
                                   '#3': [12, 15]})
        {7: [1], 3: [10, 11, 12]}

    Read the returned dictionary as saying block [1] has a partner with
    the same MD5 hash at offset 7, namely block [8], and blocks
    [10, 11, 12] have partners with the same MD5 hash at offset 3, namely
    blocks [13, 14, 15] respectively.
    """
    offset_blocks = {}
    for blknums in matching_hashes.values():
        fst_dup_blknum = blknums[0]
        snd_dup_blknum = blknums[1]
        offset = snd_dup_blknum - fst_dup_blknum
        if offset in offset_blocks:
            offset_blocks[offset].append(fst_dup_blknum)
        else:
            offset_blocks[offset] = [fst_dup_blknum]
    # Above iteration of matching_hashes dict values is probably in the
    # key (MD5 hash) order and definitely not in increasing block number
    # order.  Sort the lists of duplicate block numbers (first block
    # number of a duplicate pair).
    for key in offset_blocks.keys():
        offset_blocks[key].sort()
    return offset_blocks


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
