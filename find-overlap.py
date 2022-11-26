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

from collections import namedtuple


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
                                   '#3': [12, 15],
                                   '#4': [20, 21, 22],
                                   '#5': [25, 26, 27, 28]})
        {1: [20, 21, 25, 26, 27], 2: [20, 25, 26], 3: [10, 11, 12, 25], 7: [1]}

    Read the returned dictionary as saying blocks [20, 21, 25, 26, 27]
    have a partner with the same MD5 hash at offset 1, namely blocks
    [21, 22, 26, 27, 28] respectively, etc and finally block [1] has a
    partner with the same MD5 hash at offset 7.
    """
    offset_blocks = {}
    for blknums in matching_hashes.values():
        blknums_copy = list(blknums)
        while len(blknums_copy) >= 2:
            fst_dup_blknum = blknums_copy[0]
            blknums_copy.pop(0)
            for snd_dup_blknum in blknums_copy:
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


def find_start_matching_block(start, offset, md5_hashes):
    """Return starting block which still matches at offset

    From the start block, which is assumed to match the MD5 hash of
    block at start + offset, search backwards for the earliest block
    which still matches at block + offset.
    """
    while start > 0:
        test = start - 1
        if md5_hashes[test] != md5_hashes[test+offset]:
            break
        start = test
    return start


def find_stop_matching_block(stop, offset, md5_hashes):
    """Return first block which no longer matches at offset

    From the stop block, search forwards finding the first block which
    no longer matches at block + offset.  find_start_matching_block()
    and find_stop_matching_block() are a pair which find the Python
    slicing range [start:stop] of an overlapping range of blocks.
    """
    while stop + offset < len(md5_hashes):
        if md5_hashes[stop] != md5_hashes[stop+offset]:
            break
        stop += 1
    return stop



def compute_candidate_ranges(offset_blocks, md5_hashes):
    """Return list of candidate overlapping ranges

    From the offset blocks dictionary compute a list of candidate
    overlapping ranges.  Assumes that for each offset in the offset
    blocks dictionary there will only be one significant set of matching
    blocks, that of the overlap being searched for, and that the median
    (middle) block from the list is within that range.  (Alternatively,
    what is the chance that your file system including it's metadata
    just happens to have a set of blocks that exactly mimics the
    overlapping range being searched for.  *Incredibly* low for larger
    offset / overlap size).  The rank is calculated as the size of the
    matching range divided by the size of the offset.  (A rank of 1.0
    indicates the matching range exactly equals the offset and a valid
    overlapping data range has been found).
    """
    candidate_ranges = []
    Candidate = namedtuple('Candidate',
                          ['offset', 'start_block', 'stop_block', 'rank'])
    for offset, blocks in offset_blocks.items():
        median_index = int(round((len(blocks)) / 2))
        start_block = find_start_matching_block(blocks[median_index],
                                                offset, md5_hashes)
        stop_block = find_stop_matching_block(blocks[median_index],
                                              offset, md5_hashes)
        matching_size = stop_block - start_block
        rank = float(matching_size) / float(offset)
        candidate_ranges.append(Candidate(offset, start_block,
                                          stop_block, rank))
    candidate_ranges.sort(key=lambda c: c.rank, reverse=True)
    return candidate_ranges


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
