#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2015-2018 European Commission (JRC);
# Licensed under the EUPL 1.2+ (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl
#
"""Generic utils."""

from pathlib import Path
from typing import Optional, Union
import os
import re

import itertools as itt
import os.path as osp


_file_drive_regex = re.compile(r'^([a-z]):(/)?(.*)$', re.I)
_is_dir_regex = re.compile(r'[^/\\][/\\]$')
_unc_prefix = '\\\\?\\'


def normpath(path):
    """Like :func:`osp.normpath()`, but preserving last slash."""
    p = osp.normpath(path)
    if _is_dir_regex.search(path) and p[-1] != os.sep:
        p = p + osp.sep
    return p


def abspath(path):
    """Like :func:`osp.abspath()`, but preserving last slash."""
    p = osp.abspath(path)
    if _is_dir_regex.search(path) and p[-1] != os.sep:
        p = p + osp.sep
    return p


def convpath(fpath, abs_path=True, exp_user=True, exp_vars=True):
    """Without any flags, just pass through :func:`osp.normpath`. """
    if exp_user:
        fpath = osp.expanduser(fpath)
    if exp_vars:
        # Mask UNC '\\server\share$\path` from expansion.
        fpath = fpath.replace('$\\', '_UNC_PATH_HERE_')
        fpath = osp.expandvars(fpath)
        fpath = fpath.replace('_UNC_PATH_HERE_', '$\\')
    fpath = abspath(fpath) if abs_path else normpath(fpath)
    return fpath


def ensure_file_ext(fname, ext, *exts, is_regex=False):
    r"""
    Ensure that the filepath ends with the extension(s) specified.

    :param str ext:
        The 1st extension to search & to append if none matches,
        so must not be a regex.
    :param str exts:
        Other extensions. These may be regexes, depending on `is_regex`;
        a `'$'` is always added at its end.
    :param bool is_regex:
        When true, the rest `exts` are parsed as case-insensitive regexes.

    Example::

        >>> ensure_file_ext('foo', '.bar')
        'foo.bar'
        >>> ensure_file_ext('foo.', '.bar')
        'foo.bar'
        >>> ensure_file_ext('foo.', 'bar')
        'foo.bar'

        >>> ensure_file_ext('foo.BAR', '.bar')
        'foo.BAR'
        >>> ensure_file_ext('foo.DDD', '.bar')
        'foo.DDD.bar'

    Note that omitting dot('.') from extension does affect the results::

        >>> ensure_file_ext('foo', 'bar')
        'foo.bar'
        >>> ensure_file_ext('foo.BAR', 'bar')
        'foo.BAR'
        >>> ensure_file_ext('fooBAR', 'bar')  # File allowed without extension!
        'fooBAR'

    When more extensions are given, the 1st is appended if none matches::

        >>> ensure_file_ext('foo.xlt', '.xlsx', '.XLT')
        'foo.xlt'
        >>> ensure_file_ext('foo.xlt', '.xlsx', '.xltx')
        'foo.xlt.xlsx'

    And when regexes::

        >>> ensure_file_ext('foo.xlt', '.xlsx', r'\.xl\w{1,2}', is_regex=True)
        'foo.xlt'
        >>> ensure_file_ext('foo.xl^', '.xls', r'\.xl\w{1,2}', is_regex=True)
        'foo.xl^.xls'

    """
    if is_regex:
        ends_with_ext = any(re.search(e + '$', fname, re.IGNORECASE)
                            for e
                            in (re.escape(ext),) + exts)
    else:
        ends_with_ext = fname.lower().endswith(tuple(e.lower()
                                                     for e in (ext,) + exts))

    if not ends_with_ext:
        if fname.endswith('.'):
            fname = fname[:-1]
        if ext.startswith('.'):
            ext = ext[1:]
        return '%s.%s' % (fname, ext)

    return fname


def ensure_dir_exists(path, mode=0o755):
    """ensure that a directory exists

    If it doesn't exist, try to create it and protect against a race condition
    if another process is doing the same.

    The default permissions are 755, which differ from os.makedirs default of 777.
    """
    import errno

    if not os.path.exists(path):
        try:
            os.makedirs(path, mode=mode)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
    elif not os.path.isdir(path):
        raise OSError("%r exists but is not a directory" % path)


def find_git_root(path=None) -> Optional[Path]:
    """
    Search dirs up for a Git-repo like ``git rev-parse --show-toplevel``.

    :param path:
        where to start searching from, `cwd` if not given.
    :return:
        a `pathlib` native path, or None
    """
    if not path:
        cwd = Path()
    for f in itt.chain([cwd], cwd.resolve().parents):
        if (f / '.git').is_dir():
            return f

    # raise pvtags.GitVoidError(
    #     "Current-dir '%s' is not within a git repository!" % Path.cwd())


###################
## pathlib.Paths ##
###################

def _is_base_or_same(basepath: Path, longpath: Path, strict=False) -> Union[bool, None]:
    """
    Inverses, resolving, same-file checking, non-raising :meth:`pathlib.relative_to()`.

    :return:
        A 3-state bool denoting relativeness, or None the when they are the same;
        non-existing file(s) are still checked for relativeness
        BUT when not resolved, them surprises happen, check TCs!
        (e.g. 'BAD' considered base of 'BAD/..', but not on Linux...)

    .. TIP::
       To check if `longpath` has or `basepath` use::

           _is_base_or_same(obase, long) in (None, True)

    """
    try:
        rel = longpath.resolve(strict=strict).relative_to(basepath.resolve(strict=strict))
        return None if str(rel) == '.' else bool(rel)
    except (ValueError, FileNotFoundError):
        try:
            rel = longpath.relative_to(basepath)
            return None if str(rel) == '.' else bool(rel)
        except ValueError:
            return False


def _is_same_file(fp1: Path, fp2: Path) -> Union[bool, None]:
    """
    Non-raising version of pathlib.

    :return:
        a 3-state bool denoting sameness, or None if non-existing file(s) involved.
    """
    try:
        return fp1.samefile(fp2)
    except FileNotFoundError:
        return None
