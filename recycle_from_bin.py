#! /usr/bin/python
#
# recycle_from_bin.py: move files and rename from Windows Recycle Bin directory
# by pts@fazekas.hu at Wed Mar 15 23:18:55 CET 2023
#
# This program works in Python 2.4, 2.5, 2.6 or 2.7 (not 3.x) on a Unix system
# (not Windows) with UTF-8 pathname encoding.
#

import os
import os.path
import stat
import struct
import sys


def parse_recycle_bin_i_file(filename):
  # Based on: https://stackoverflow.com/q/66939004
  f = open(filename, 'rb')
  try:
    data = f.read(0x18)
    if len(data) != 0x18:
      raise ValueError('EOF in Recycle Bin $I file header.')
    version, size, deletion_filetime = struct.unpack('<QQQ', data)
    if version == 1:
      deleted_pathname = f.read(520)
    elif version == 2:
      data = f.read(4)
      if len(data) != 4:
        raise ValueError('EOF in deleted_pathname size.')
      deleted_pathname_size, = struct.unpack('<L', data)
      if deleted_pathname_size > 0x1000:
        raise ValueError('deleted_pathname too long.')
      deleted_pathname = f.read(deleted_pathname_size << 1)
    else:
      raise ValueError('Bad Recycle Bin $I signature: version=%d' % version)
  finally:
    f.close()
  try:
    deleted_pathname = deleted_pathname.decode('utf-16le').encode('utf-8')
  except (UnicodeDecodeError, UnicodeEncodeError, ValueError):
    raise ValueError('Bad UTF-16LE pathname: %r' % deleted_pathname)
  i = deleted_pathname.find('\0')
  if i < 0:
    raise ValueError('Missing trailing NUL in deleted_pathname.')
  deleted_pathname = deleted_pathname[:i]
  if len(deleted_pathname) < 3:
    raise ValueError('deleted_pathame too short: %r' % deleted_pathname)
  if not deleted_pathname[0].isalpha():
    raise ValueError('Bad drive letter in deleted_pathname: %r' % deleted_pathname)
  if deleted_pathname[1 : 3] != ':\\':
    raise ValueError('Missing drive separator in deleted_pathname: %r' % deleted_pathname)
  deleted_pathname = os.path.join(*filter(None, (
      deleted_pathname[0].lower() + deleted_pathname[2:]).split('\\')))
  return size, deletion_filetime, deleted_pathname


def filetime_to_timestamp_float(filetime):
  """Convert a Windows FILETIME (64-bit integer) to a Unix timestamp float."""
  # Based on: https://stackoverflow.com/a/6161842
  WINDOWS_TICK = 10000000.
  SEC_TO_UNIX_EPOCH = 11644473600
  return (filetime / WINDOWS_TICK) - SEC_TO_UNIX_EPOCH


def process_recycle_bin_pathname(pathname, restore_target_dir):
  basename = os.path.basename(pathname)
  if not basename.startswith('$I'):
    raise ValueError('Expected Recycle Bin $I pathname: %s' % pathname)
  r_pathname = os.path.join(os.path.dirname(pathname), '$R' + basename[2:])
  try:
    stat_obj = os.lstat(r_pathname)
  except OSError:
    return  # Silently ignore.
  sys.stderr.write('info: moving from Recycle Bin: %s\n' % r_pathname)
  (size, deletion_filetime, deleted_pathname
  ) = parse_recycle_bin_i_file(pathname)
  if stat.S_ISREG(stat_obj.st_mode) and size != stat_obj.st_size:
    sys.stderr.write('warning: file size mismatch, not moving: %s\n' % r_pathname)
    return
  deletion_timestamp = filetime_to_timestamp_float(deletion_filetime)
  if deletion_timestamp < stat_obj.st_mtime:
    os.utime(r_pathname, (stat_obj.st_atime, deletion_timestamp))
  if restore_target_dir == '.':
    restore_pathname = deleted_pathname
  else:
    restore_pathname = os.path.join(restore_target_dir, deleted_pathname)
  sys.stderr.write('info: moving to: %s\n' % restore_pathname)
  restore_dirname = os.path.dirname(restore_pathname)
  if not os.path.isdir(restore_dirname):
    os.makedirs(restore_dirname)
  if os.path.exists(restore_pathname):
    prefix, ext = os.path.splitext(restore_pathname)
    i = 1
    while 1:
      restore_pathname = '%s-%d%s' % (prefix, i, ext)
      if not os.path.exists(restore_pathname):
        break
      i += 1
  os.rename(r_pathname, restore_pathname)
  os.remove(pathname)


def process_recursively(pathname, restore_target_dir):
  try:
    stat_obj = os.stat(pathname)
  except OSError:
    return  # Silently ignore, probably it's an $R file which has been moved.
  if stat.S_ISDIR(stat_obj.st_mode):
    for entry in sorted(os.listdir(pathname)):
      process_recursively(os.path.join(pathname, entry), restore_target_dir)
  elif stat.S_ISREG(stat_obj.st_mode):
    basename = os.path.basename(pathname)
    if basename.startswith('$I'):
      process_recycle_bin_pathname(pathname, restore_target_dir)


def main(argv):
  if len(argv) < 2 or argv[1] == '--help':
    sys.stderr.write('Usage: %s <recycle-bin-dir>\n' % argv[0])
    sys.exit(1)
  i = 1
  while i < len(argv):
    arg = argv[i]
    i += 1
    if not arg.startswith('-'):
      i -= 1
      break
    elif arg == '--':
      break
    else:
      sys.stderr.write('fatal: unknown command-line flag: %s\n' % arg)
      sys.exit(1)
  if i == len(argv):
    sys.stderr.write('fatal: missing <recycle-bin-dir>\n')
    sys.exit(1)
  pathname = argv[i]
  i += 1
  if i != len(argv):
    sys.stderr.write('fatal: too many command-line arguments\n')
    sys.exit(1)
  restore_target_dir = '.'
  process_recursively(pathname, restore_target_dir)


if __name__ == '__main__':
  sys.exit(main(sys.argv))
