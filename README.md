![find-overlap-banner](find-overlap-banner.png)


find-overlap.py
===============

`find-overlap.py` is a command line tool which reads a file system (or
any other data) and finds the overlapping range after an interrupted
GParted resize/move.

Works by computing the MD5 hash of every block and finding blocks with
a duplicate copy to identify the overlap size and location.  Takes as
long to run as reading the named device.


Example
-------

```
# find-overlap.py --dump-hashes /tmp/hashes.txt -- /dev/sdb1
Block size: 1048576 bytes

Overlap of size 4096 blocks found.
Range [4321:8417) overlaps [8417:12513).
Original file system size was 16384 blocks.
Restore original file system with:
    dd if=INPUT bs=1048576 count=6369 of=OUTPUT
    dd if=INPUT bs=1048576 skip=10465 seek=6369 of=OUTPUT
```

Use of the `--dump-hashes` option is recommended as it avoids having to
read the file system again if you need to re-run the command.  See
`--read-hashes` option.  Also the dump file must be provided when users
request help.


Recommended recovery actions
----------------------------

If you don't know what caused the interruption to the resize/move, or
you know it was a drive fault, then follow these steps:
1. Use [ddrescue](https://www.gnu.org/software/ddrescue/) to copy the
   damaged file system to a new drive.
   * [Google search "how to use ddrescue"](https://www.google.com/search?q=how%20to%20use%20ddrescue)
   * [ddrescue manaual](https://www.gnu.org/software/ddrescue/manual/ddrescue_manual.html)
2. Run `find-overlap.py` on the copy.
3. Only run the second `dd` command specifying both the `INPUT` and
   `OUTPUT` as the partition on the new drive containing the copy.

If you know the cause of the interruption to the resize/move was not a
drive fault (for example manual cancellation, software crash or power
failure) then follow these steps:
1. Run `find-overlay.py` on the damaged file system.
2. Run both `dd` commands to copy the 2 pieces of the file system to a
   new partition.
