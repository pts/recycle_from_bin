#! /usr/bin/python
#
# recycle_from_bin.py: move files and rename from Windows Recycle Bin directory
# by pts@fazekas.hu at Wed Mar 15 23:18:55 CET 2023
#
# This program works in Python 2.4, 2.5, 2.6 or 2.7 (not 3.x) on Linux,
# macOS (and other Unix-like systems) and Windows. It fully supports
# filenames containing any character (even non-ASCII) on all platforms. On
# Windows, console messages use the UTF-8 encoding, so filenames with
# non-ASCII characters are displayed incurrectly (but the files are
# processed correctly).
#

import os
import os.path
import stat
import struct
import sys


if sys.platform.startswith('win'):
  def pathname_to_os(pathname):
    if not isinstance(pathname, str):
      raise TypeError
    return pathname.decode('utf-8')  # Returns unicode.

  def pathnames_from_os(pathnames):
    output = []
    for pathname in pathnames:
      if not isinstance(pathname, unicode):
        raise TypeError
      output.append(pathname.encode('utf-8'))  # str.
    return output

  def pathname_from_argv(pathname):
    if not isinstance(pathname, str):
      raise TypeError
    mb = pathname.decode('mbcs')  # Windows-specific.
    return mb.encode('utf-8')  # Returns str.

  def get_filesystem_encoding():
    return 'utf-8'  # Fake, to be used with pathname_to_os.

  # Console message will still be wrong (using UTF-8 encoding).

  try:
    os.lstat
  except AttributeError:
    os.lstat = os.stat  # Not needed in Python 2.6.
else:
  def pathname_to_os(pathname):
    if not isinstance(pathname, str):
      raise TypeError
    return pathname  # Returns str.

  def pathnames_from_os(pathnames):
    output = []
    for pathname in pathnames:
      if not isinstance(pathname, str):
        raise TypeError
      output.append(pathname)
    return output

  def pathname_from_argv(pathname):
    if not isinstance(pathname, str):
      raise TypeError
    return pathname  # Returns str.

  def get_filesystem_encoding(_cache=[]):
    if not _cache:
      fsenc = sys.getfilesystemencoding().lower()  # 'ANSI_X3.4-1968' for LC_CTYPE=C on Linux.
      if fsenc.startswith('ansi') and '1968' in fsenc:
        fsenc = 'utf-8'
      elif 'ascii' in fsenc or not fsenc or fsenc == 'c':
        fsenc = 'utf-8'
      _cache.append(fsenc)
    return _cache[0]


def maybe_encode_pathname(pathname):
  if not isinstance(pathname, unicode):
    raise TypeError
  filesystem_encoding = get_filesystem_encoding()
  try:
    return pathname.encode(filesystem_encoding)
  except (UnicodeEncodeError, ValueError):
    raise ValueError('Cannot encode pathname as %s: %r' % (filesystem_encoding, pathname))


def parse_recycle_bin_i_file(filename):
  # Based on: https://stackoverflow.com/q/66939004
  f = open(pathname_to_os(filename), 'rb')
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
    deleted_pathname = deleted_pathname.decode('utf-16le')
  except (UnicodeDecodeError, ValueError):
    raise ValueError('Bad UTF-16LE pathname: %r' % deleted_pathname)
  deleted_pathname = maybe_encode_pathname(deleted_pathname)
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
    stat_obj = os.lstat(pathname_to_os(r_pathname))
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
    os.utime(pathname_to_os(r_pathname), (stat_obj.st_atime, deletion_timestamp))
  if restore_target_dir == '.':
    restore_pathname = deleted_pathname
  else:
    restore_pathname = os.path.join(restore_target_dir, deleted_pathname)
  if os.path.exists(pathname_to_os(restore_pathname)):
    prefix, ext = os.path.splitext(restore_pathname)
    i = 1
    while 1:
      restore_pathname = '%s-%d%s' % (prefix, i, ext)
      if not os.path.exists(pathname_to_os(restore_pathname)):
        break
      i += 1
  sys.stderr.write('info: moving to: %s\n' % restore_pathname)
  restore_dirname = os.path.dirname(restore_pathname)
  if not os.path.isdir(pathname_to_os(restore_dirname)):
    os.makedirs(pathname_to_os(restore_dirname))
  os.rename(pathname_to_os(r_pathname), pathname_to_os(restore_pathname))
  os.remove(pathname_to_os(pathname))


def process_recursively(pathname, restore_target_dir):
  try:
    stat_obj = os.lstat(pathname_to_os(pathname))
  except OSError:
    return  # Silently ignore, probably it's an $R file which has been moved.
  if stat.S_ISDIR(stat_obj.st_mode):
    for entry in sorted(pathnames_from_os(os.listdir(pathname_to_os(pathname)))):
      process_recursively(os.path.join(pathname, entry), restore_target_dir)
  elif stat.S_ISREG(stat_obj.st_mode):
    basename = os.path.basename(pathname)
    if basename.startswith('$I'):
      process_recycle_bin_pathname(pathname, restore_target_dir)


def main(argv):
  if len(argv) < 2 or argv[1] == '--help':
    sys.stderr.write(
        'Usage: %s [<flag> ...] <recycle-bin-dir>\nFlags:\n'
        '--restore-target-dir=<dir>: Restore recycled files to here.\n'
        % argv[0])
    sys.exit(1)
  restore_target_dir = '.'
  i = 1
  while i < len(argv):
    arg = argv[i]
    i += 1
    if not arg.startswith('-'):
      i -= 1
      break
    elif arg == '--':
      break
    elif arg.startswith('--restore-target-dir='):
      restore_target_dir = pathname_from_argv(arg[arg.find('=') + 1:])
    else:
      sys.stderr.write('fatal: unknown command-line flag: %s\n' % arg)
      sys.exit(1)
  if i == len(argv):
    sys.stderr.write('fatal: missing <recycle-bin-dir>\n')
    sys.exit(1)
  pathname = pathname_from_argv(argv[i])
  i += 1
  if i != len(argv):
    sys.stderr.write('fatal: too many command-line arguments\n')
    sys.exit(1)
  process_recursively(pathname, restore_target_dir)


if __name__ == '__main__':
  sys.exit(main(sys.argv))
