#!/usr/bin/env python
# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (c) 2022 Mike Fleetwood
# FILE: find-overlap.py

"""find-overlap.py - Find overlapping range of a file system

Command line tool which reads a file system (or any other data) and
finds the overlapping range after an interrupted GParted resize/move.

Works by computing the MD5 hash of every block and finding blocks with
a duplicate copy to identify the overlap size and location.  Takes as
long to run as reading the named device.

Command line usage:
    find-overlap.py [DEVICE]
"""


import argparse
import hashlib
import sys

from collections import namedtuple


PROGNAME = 'find-overlap.py'
BLOCKSIZE = 1024*1024


dump_hashes_fname = None


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
    for key, value in list(matching_hashes.items()):
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
                          ['offset', 'start_block', 'stop_block',
                           'total_blocks', 'rank'])
    for offset, blocks in offset_blocks.items():
        median_index = int(round((len(blocks)) / 2))
        start_block = find_start_matching_block(blocks[median_index],
                                                offset, md5_hashes)
        stop_block = find_stop_matching_block(blocks[median_index],
                                              offset, md5_hashes)
        matching_size = stop_block - start_block
        rank = float(matching_size) / float(offset)
        candidate_ranges.append(Candidate(offset, start_block, stop_block,
                                          len(md5_hashes), rank))
    candidate_ranges.sort(key=lambda c: c.rank, reverse=True)
    return candidate_ranges


def candidate_is_full_range(candidate_range):
    """Return true if the size of matching range is the size of the
    offset

    Allow the matching range to be 1 block less in case of a failure to
    copy one block.
    """
    matching_size = candidate_range.stop_block - candidate_range.start_block
    return matching_size + 1 >= candidate_range.offset


def candidate_range_is_large_enough(candidate_range):
    """Exclude offsets of 2 or less because accepting groups of up to 4
    block allows 4 blocks in a row with the same MD5 hash to be found as
    an overlapping data range of 2 blocks.
    """
    matching_size = candidate_range.stop_block - candidate_range.start_block
    return matching_size > 2


def dump_hashes(fname, md5_hashes, matching_hashes):
    """Write substitute hashes to the named hashes dump file

    The 128-bit (16 byte) binary MD5 hashes are substituted by '#%d'
    where '%d' is the first block number with that hash.  Each
    substitute hash is written on a separate line.  Start of an example
    hash dump file:
        #0
        #1
        #2
    """
    try:
        f = open(fname, mode='w')
    except IOError as e:
        sys.exit(PROGNAME + ': ' + str(e))
    for md5_hash in md5_hashes:
        f.write('#%d\n' % (matching_hashes[md5_hash][0]))
    f.close()
    

def find_overlap_from_hashes(md5_hashes):
    """Return list of validated overlapping ranges from list of MD5
    hashes
    """
    matching_hashes = generate_matching_hashes(md5_hashes)
    if dump_hashes_fname:
        dump_hashes(dump_hashes_fname, md5_hashes, matching_hashes)
    eliminate_non_duplicates(matching_hashes)
    offset_blocks = compute_offset_blocks(matching_hashes)
    candidate_ranges = compute_candidate_ranges(offset_blocks, md5_hashes)
    candidate_ranges = list(filter(candidate_is_full_range, candidate_ranges))
    candidate_ranges = list(filter(candidate_range_is_large_enough,
                                   candidate_ranges))
    return candidate_ranges


def print_overlap(cr):
    """Print one overlapping range"""
    print('Overlap of size %d blocks found.' % (cr.offset))
    print('Range [%d:%d) overlaps [%d:%d).' %
          (cr.start_block, cr.stop_block,
           cr.start_block + cr.offset, cr.stop_block + cr.offset))
    print ('Original file system size was %d blocks.' %
           (cr.total_blocks - cr.offset))
    median_block = int(round((cr.start_block + cr.stop_block) / 2))
    print('Restore original file system with:')
    print('    dd if=INPUT bs=%d count=%d of=OUTPUT' %
          (BLOCKSIZE, median_block))
    print('    dd if=INPUT bs=%d skip=%d seek=%d of=OUTPUT' %
          (BLOCKSIZE, median_block + cr.offset, median_block))


def print_overlap_output(candidate_ranges):
    """Print the list of overlapping ranges"""
    if len(candidate_ranges) == 0:
        print('No overlapping range found')
        return
    print('Block size: %d bytes' % (BLOCKSIZE))
    if len(candidate_ranges) > 1:
        print('WARNING: Multiple overlapping ranges found')
    for cr in candidate_ranges:
        print('')
        print_overlap(cr)


def find_overlap_from_open_hashes_file(f):
    """Read hashes from previous dump file, search for the overlapping
    range and print the results
    """
    md5_hashes = f.read().splitlines()
    candidate_ranges = find_overlap_from_hashes(md5_hashes)
    print_overlap_output(candidate_ranges)


def find_overlap_from_open_file(f):
    """Search for the overlapping range and print the findings"""
    md5_hashes = read_hashes(f)
    candidate_ranges = find_overlap_from_hashes(md5_hashes)
    print_overlap_output(candidate_ranges)


def main(args=None):
    """Parse command line arguments and calls the function to search for
    the overlapping range in the named device or stdin
    """
    global dump_hashes_fname
    parser = argparse.ArgumentParser(description="""
        Find overlapping portion of a file system after an interrupted
        GParted resize/move.""")
    parser.add_argument('--read-hashes', dest='read_hashes_fname',
                        metavar='DUMP_FILE', help="""
        Read previously saved hashes from this file instead of reading
        from stdin or named device""")
    parser.add_argument('--dump-hashes', dest='dump_hashes_fname',
                        metavar='DUMP_FILE', help='Write hashes to this file')
    parser.add_argument('device', nargs='?', help="""
        optional device or file to read""")
    args = parser.parse_args(args)
    dump_hashes_fname = args.dump_hashes_fname
    if args.read_hashes_fname:
        try:
            f = open(args.read_hashes_fname, mode='r')
        except IOError as e:
            return PROGNAME + ': ' + str(e)
        find_overlap_from_open_hashes_file(f)
        f.close()
    elif args.device:
        try:
            f = open(args.device, mode='rb')
        except IOError as e:
            return PROGNAME + ': ' + str(e)
        find_overlap_from_open_file(f)
        f.close()
    else:
        find_overlap_from_open_file(sys.stdin)


if __name__ == '__main__':
    sys.exit(main())
