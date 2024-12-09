#!/usr/bin/env python

import argparse
import hashlib
import os
import signal
import sys
import time
from collections import namedtuple
from tqdm import tqdm  # For progress bar

PROGNAME = 'find-overlap.py'
BLOCKSIZE = 1024*1024  # 1 MiB
TEMP_HASH_FILE = 'hashes.tmp'

# Global variable to track interruption
terminate = False

def signal_handler(sig, frame):
    """Handle terminal signals to enable graceful shutdown."""
    global terminate
    print("\nTerminate signal received. Saving progress...")
    terminate = True

dump_hashes_fname = None

def read_hashes(f, total_blocks, start_block=0):
    """Return list of MD5 hashes for all blocks read from the open file"""
    md5_hashes = []
    progress = tqdm(total=total_blocks, initial=start_block, unit='blocks', desc='Processing')
    f.seek(start_block * BLOCKSIZE)
    current_block = start_block
    last_save_time = time.time()
    
    while not terminate:
        data = f.read(BLOCKSIZE)
        if not data:
            break
        md5_hash = hashlib.md5(data).digest()
        md5_hashes.append(md5_hash)
        current_block += 1
        progress.update(1)

        # Save progress every minute
        if time.time() - last_save_time >= 60:
            save_hashes(md5_hashes, current_block)
            last_save_time = time.time()

    progress.close()
    save_hashes(md5_hashes, current_block)
    return md5_hashes


def save_hashes(md5_hashes, processed_blocks, filename=TEMP_HASH_FILE):
    """Save computed hashes and progress to a temporary file."""
    with open(TEMP_HASH_FILE, 'w') as temp_file:
        temp_file.write(f"{processed_blocks}\n")
        for md5_hash in md5_hashes:
            temp_file.write(md5_hash.hex() + '\n')


def generate_matching_hashes(md5_hashes):
    matching_hashes = {}
    for blknum, md5_hash in enumerate(md5_hashes):
        matching_hashes.setdefault(md5_hash, []).append(blknum)
    return matching_hashes


def eliminate_non_duplicates(matching_hashes):
    for key, value in list(matching_hashes.items()):
        if len(value) < 2 or len(value) > 4:
            del matching_hashes[key]


def compute_offset_blocks(matching_hashes):
    offset_blocks = {}
    for blknums in matching_hashes.values():
        for i in range(len(blknums)):
            for j in range(i + 1, len(blknums)):
                offset = blknums[j] - blknums[i]
                offset_blocks.setdefault(offset, []).append(blknums[i])
    for key in offset_blocks:
        offset_blocks[key].sort()
    return offset_blocks


def find_start_matching_block(start, offset, md5_hashes):
    while start > 0:
        if md5_hashes[start - 1] != md5_hashes[start + offset - 1]:
            break
        start -= 1
    return start


def find_stop_matching_block(stop, offset, md5_hashes):
    while stop + offset < len(md5_hashes):
        if md5_hashes[stop] != md5_hashes[stop+offset]:
            break
        stop += 1
    return stop


def compute_candidate_ranges(offset_blocks, md5_hashes):
    candidate_ranges = []
    Candidate = namedtuple('Candidate',
                          ['offset', 'start_block', 'stop_block',
                           'total_blocks', 'rank'])
    for offset, blocks in offset_blocks.items():
        median_index = len(blocks) // 2
        start_block = find_start_matching_block(blocks[median_index],
                                                offset, md5_hashes)
        stop_block = find_stop_matching_block(blocks[median_index],
                                              offset, md5_hashes)
        matching_size = stop_block - start_block
        rank = matching_size / offset
        candidate_ranges.append(Candidate(offset, start_block, stop_block,
                                          len(md5_hashes), rank))
    candidate_ranges.sort(key=lambda c: c.rank, reverse=True)
    return candidate_ranges


def candidate_is_full_range(candidate_range):
    matching_size = candidate_range.stop_block - candidate_range.start_block
    return matching_size + 1 >= candidate_range.offset


def candidate_range_is_large_enough(candidate_range):
    matching_size = candidate_range.stop_block - candidate_range.start_block
    return matching_size > 2


def dump_hashes(fname, md5_hashes, matching_hashes):
    try:
        f = open(fname, mode='w')
    except IOError as e:
        sys.exit(PROGNAME + ': ' + str(e))
    for md5_hash in md5_hashes:
        f.write('#%d\n' % (matching_hashes[md5_hash][0]))
    f.close()
    

def find_overlap_from_hashes(md5_hashes):
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
    print('Range [%d:%d] overlaps [%d:%d].' %
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
    if len(candidate_ranges) == 0:
        print('No overlapping range found')
        return
    print('Block size: %d bytes' % (BLOCKSIZE))
    if len(candidate_ranges) > 1:
        print('WARNING: Multiple overlapping ranges found')
    for cr in candidate_ranges:
        print('')
        print_overlap(cr)


def load_hashes(filename=TEMP_HASH_FILE):
    if not os.path.exists(filename):
        return [], 0
    with open(filename, 'r') as temp_file:
        lines = temp_file.readlines()
        processed_blocks = int(lines[0].strip())
        md5_hashes = [bytes.fromhex(line.strip()) for line in lines[1:]]
    return md5_hashes, processed_blocks


def find_overlap_from_open_file(f):
    file_size = f.seek(0, 2)
    f.seek(0)

    total_blocks = file_size // BLOCKSIZE
    print(f"DEBUG: File size is {file_size} bytes, which is {total_blocks} blocks.")

    if total_blocks == 0:
        print("ERROR: File size is zero or file is too small to process.")
        return

    md5_hashes, processed_blocks = load_hashes()
    if processed_blocks < total_blocks:
        md5_hashes.extend(read_hashes(f, total_blocks, processed_blocks))
    find_overlap_from_hashes(md5_hashes)
    print_overlap_output(candidate_ranges)


def main(args=None):
    signal.signal(signal.SIGINT, signal_handler)
    parser = argparse.ArgumentParser(description="""
        Find overlapping portion of a file system after an interrupted
        GParted resize/move.""")
    parser.add_argument('--read-hashes', metavar='FILE', help="""
        Read previously saved hashes from this file instead of reading
        from stdin or named device""")
    parser.add_argument('device', nargs='?', help="""
        optional device or file to read""")
    args = parser.parse_args(args)

    if args.read_hashes:
        try:
            with open(args.read_hashes, mode='r') as f:
                md5_hashes, _ = load_hashes(args.read_hashes)
                candidate_ranges = find_overlap_from_hashes(md5_hashes)
                print_overlap_output(candidate_ranges)
        except IOError as e:
            return PROGNAME + ': ' + str(e)
    elif args.device:
        try:
            f = open(args.device, mode='rb')
        except IOError as e:
            return PROGNAME + ': ' + str(e)
        find_overlap_from_open_file(f)
    else:
        print("No input provided. Use --read-hashes or specify a device.")
        sys.exit(1)


if __name__ == '__main__':
    sys.exit(main())
