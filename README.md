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
