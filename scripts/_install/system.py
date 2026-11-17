"""The operating system calls the installer needs, for POSIX and for Windows.

On Windows a skill link is a directory junction, because a symlink needs Developer Mode or an elevated process.
"""

from __future__ import annotations

import errno
import os
import shlex
import shutil
import stat
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

WINDOWS = os.name == "nt"

if WINDOWS:
    import _winapi
    import msvcrt
else:
    import fcntl

NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)

# Windows CreateFile arguments: read attributes only, share read, write and delete, open the reparse point itself.
_READ_ATTRIBUTES = 0x80
_SHARE_ALL = 0x7
_OPEN_EXISTING = 3
_BACKUP_SEMANTICS = 0x02000000
_OPEN_REPARSE_POINT = 0x00200000
_VERBATIM = "\\\\?\\"


def is_junction(path):
    if not WINDOWS:
        return False
    try:
        info = os.lstat(path)
    except (OSError, ValueError):
        return False
    return bool(info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT) and info.st_reparse_tag == stat.IO_REPARSE_TAG_MOUNT_POINT


def is_link(path):
    """Whether `path` is a symlink or, on Windows, a directory junction."""
    return os.path.islink(path) or is_junction(path)


def read_link(path):
    """The target text of the link at `path`. Windows spells a junction target with the \\\\?\\ prefix, which this drops."""
    text = os.readlink(path)
    if WINDOWS and text.startswith(_VERBATIM):
        text = text[len(_VERBATIM):]
        if text.startswith("UNC\\"):
            text = "\\" + text[3:]
    return text


def make_link(target, path):
    """Link the directory `path` to the directory `target`. A junction on Windows, a symlink elsewhere."""
    if WINDOWS:
        _winapi.CreateJunction(str(target), str(path))
    else:
        os.symlink(target, path, target_is_directory=True)


def move(path, target):
    """Move the entry at `path` to `target`, as shutil.move does, except that a junction moves as a junction.

    shutil.move does not see a junction as a link, so across volumes it would copy the directory the junction names.
    """
    if not is_junction(path):
        shutil.move(path, target)
        return
    try:
        os.rename(path, target)
    except OSError as error:
        if error.errno != errno.EXDEV:
            raise
        make_link(read_link(path), target)
        os.unlink(path)


def command_line(words):
    """One command line a person can paste into this platform's usual shell."""
    if WINDOWS:
        return subprocess.list2cmdline(["python" if word == "python3" else word for word in words])
    return shlex.join(words)


def same_path(one, other):
    return os.path.normcase(os.path.normpath(one)) == os.path.normcase(os.path.normpath(other))


def identity(info):
    """The fields that tell one entry from another. Windows reports the creation time where POSIX reports the change time."""
    if WINDOWS:
        return info.st_dev, info.st_ino, getattr(info, "st_birthtime_ns", info.st_ctime_ns)
    return info.st_dev, info.st_ino, info.st_ctime_ns


if WINDOWS:
    HOLD_FLAGS = 0
elif hasattr(os, "O_PATH"):
    # Linux opens the entry itself with O_PATH.
    HOLD_FLAGS = os.O_PATH | os.O_NOFOLLOW
else:
    # macOS opens a symlink itself with O_SYMLINK, and O_NONBLOCK keeps a FIFO from blocking.
    HOLD_FLAGS = os.O_RDONLY | getattr(os, "O_SYMLINK", os.O_NOFOLLOW) | os.O_NONBLOCK


def open_entry(path):
    """Open the entry at `path` itself, a link or a directory included, and return a descriptor os.fstat reads.

    On Windows the handle shares delete access, so the entry can still be renamed while it is held.
    """
    if not WINDOWS:
        return os.open(path, HOLD_FLAGS)
    handle = _winapi.CreateFile(os.fspath(path), _READ_ATTRIBUTES, _SHARE_ALL, 0, _OPEN_EXISTING,
                                _BACKUP_SEMANTICS | _OPEN_REPARSE_POINT, 0)
    try:
        return msvcrt.open_osfhandle(handle, os.O_RDONLY)
    except BaseException:
        _winapi.CloseHandle(handle)
        raise


def rename_noreplace_windows(source, target):
    """Rename `source` to `target` only while `target` is empty. Return 0, or the errno that stopped it.

    MoveFileEx without MOVEFILE_REPLACE_EXISTING refuses a target that exists, so os.rename never replaces on Windows.
    """
    try:
        os.rename(source, target)
    except FileExistsError:
        return errno.EEXIST
    except OSError as error:
        return error.errno or errno.EIO
    return 0


def remove_empty_dirs(paths):
    """Remove each directory in `paths` in order, deepest first, while it is empty and is not a link.

    The first one that is a link or cannot be removed ends it. For platforms whose os.rmdir takes no dir_fd.
    """
    for path in paths:
        if is_link(path) or not os.path.isdir(path):
            return
        try:
            os.rmdir(path)
        except OSError:
            return


LOCK_NAME = ".install.lock"


@contextmanager
def locked(state):
    """Hold the installer's lock on the state directory until the block ends.

    POSIX takes flock on the directory itself. Windows cannot open a directory as a file, so it locks the first byte
    of LOCK_NAME inside it, retrying until the other run lets go.
    """
    state = Path(state)
    state.mkdir(parents=True, exist_ok=True)
    if not WINDOWS:
        fd = os.open(state, os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        return
    fd = os.open(state / LOCK_NAME, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        while True:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                break
            except OSError as error:
                if error.errno not in (errno.EACCES, errno.EDEADLK):
                    raise
                time.sleep(0.1)
        try:
            yield
        finally:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    finally:
        os.close(fd)
