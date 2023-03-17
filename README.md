# recycle_from_bin.py: restore files from Windows Recycle Bin directory

recycle_from_bin.py is a command-line tool Python script which restores all
files (by moving and renaming them) from a Windows Recycle Bin directory. It
works with and 3 (>= 3.0) and Python 2 (>= 2.4), and it works on Linux,
macOS (and other Unix-like systems) and Windows.

By default it restores files into the subdirectories of the current
directory, keeping the original pathname components.

It doesn't overwrite files in the restore target directory, but it appends a
number to the filename to disambiguate.

It works for filenames contaning any characters (even non-ASCII).

Example usage on Linux:

```
  ./recycle_from_bin.py /media/foo/bar/'$Recycle.Bin'
```

Example usage on Windows:

```
  python recycle_from_bin.py "C:\$Recycle.Bin"
```
