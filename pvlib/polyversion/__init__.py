#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
"""
Python-2.7-safe, no-deps code to discover sub-project versions in Git *polyvers* monorepos.

The *polyvers* version-configuration tool is generating **pvtags** like::

    proj-foo-v0.1.0

And assuming :func:`polyversion()` is invoked from within a Git repo, it may return
either ``0.1.0`` or ``0.1.0+2.gcaffe00``, if 2 commits have passed since
last *pvtag*.

Also, this library function as a *setuptools* "plugin" (see :mod:`setuplugin`).

Finally, the wheel can be executed like that::

    python polyversion-*.whl --help

"""
from __future__ import print_function

import logging
import sys

import os.path as osp


__all__ = 'polyversion polytime'.split()


log = logging.getLogger(__name__)


#: A 2-tuple containing 2 ``{vprefix}`` values for the patterns below,for
#: for *version-tags* and *release-tags* respectively.
tag_vprefixes = ('v', 'r')

#: The default pattern for *monorepos* version-tags,
#: receiving 3 :pep:`3101` interpolation parameters::
#:
#:     {pname}, {version} = '*', {vprefix} = tag_vprefixes[0 | 1]
#:
#: The match patterns for ``git describe --match <pattern>`` are generated by this.
pvtag_format = '{pname}-{vprefix}{version}'
#: Like :data:`pvtag_format` but for *mono-project* version-tags.
vtag_format = '{vprefix}{version}'

#: The default regex pattern breaking :term:`monorepo` version-tags
#: and/or ``git-describe`` output into 3 capturing groups:
#:
#:   - ``pname``,
#:   - ``version`` (without the ``{vprefix)``),
#:   - ``descid`` (optional) anything following the dash('-') after
#:     the version in ``git-describe`` result.
#:
#: It is given 2 :pep:`3101` interpolation parameters::
#:
#:     {pname}, {vprefix} = tag_vprefixes[0 | 1]
#:
#: See :pep:`0426` for project-name characters and format.
pvtag_regex = r"""(?xmi)
    ^(?P<pname>{pname})
    -
    {vprefix}(?P<version>\d[^-]*)
    (?:-(?P<descid>\d+-g[a-f\d]+))?$
"""
#: Like :data:`pvtag_format` but for :term:`mono-project` version-tags.
vtag_regex = r"""(?xmi)
    ^(?P<pname>)
    {vprefix}(?P<version>\d[^-]*)
    (?:-(?P<descid>\d+-g[a-f\d]+))?$
"""


def _clean_cmd_result(res):  # type: (bytes) -> str
    """
    :return:
        only if there is something in `res`, as utf-8 decoded string
    """
    res = res and res.strip()
    if res:
        return res.decode('utf-8', errors='surrogateescape')


def rfc2822_tstamp(nowdt=None):
    """Py2.7 code from https://stackoverflow.com/a/3453277/548792"""
    from datetime import datetime
    import time
    from email import utils

    if nowdt is None:
        nowdt = datetime.now()
    nowtuple = nowdt.timetuple()
    nowtimestamp = time.mktime(nowtuple)
    now = utils.formatdate(nowtimestamp, localtime=True)

    return now


def _my_run(cmd, cwd):
    import subprocess as sbp

    "For commands with small output/stderr."
    if not isinstance(cmd, (list, tuple)):
        cmd = cmd.split()
    proc = sbp.Popen(cmd, stdout=sbp.PIPE, stderr=sbp.PIPE,
                     cwd=str(cwd), bufsize=-1)
    res, err = proc.communicate()

    if proc.returncode != 0:
        log.error('%s\n  cmd: %s', err, cmd)
        raise sbp.CalledProcessError(proc.returncode, cmd)
    else:
        return _clean_cmd_result(res)


def _caller_module_name(nframes_back=2):
    import inspect

    frame = inspect.currentframe()
    try:
        for _ in range(nframes_back):
            frame = frame.f_back
        modname = frame.f_globals['__name__']
        name = modname.split('.')[-1]
        if name.startswith('_'):  # eg: _version, __init__, __main__
            raise ValueError(
                "Auto-derived project-name from module '%s' starts with underscore!" %
                modname)
        return name
    finally:
        del frame


def _caller_fpath(nframes_back=2):
    import inspect

    frame = inspect.currentframe()
    try:
        for _ in range(nframes_back):
            frame = frame.f_back
        fpath = inspect.getframeinfo(frame).filename

        return osp.dirname(fpath)
    finally:
        del frame


def split_pvtag(pvtag, tag_regexes):
    if not isinstance(tag_regexes, (list, tuple)):
        raise ValueError("Expected `tag_regexes` as list-of-str, got: %r" %
                         tag_regexes)

    for tregex in tag_regexes:
        try:
            m = tregex.match(pvtag)
            if m:
                mg = m.groupdict()
                return mg['pname'], mg['version'], mg['descid']
        except Exception as ex:
            log.error("Matching pvtag '%s' by '%s' failed due to: %s",
                      pvtag, tregex.pattern, ex)
            raise

    raise ValueError(
        "Unparseable pvtag %r from pvtag_regexes: %s!" %
        (pvtag, ''.join('\n- %s' % tregex.pattern
                        for tregex in tag_regexes)))


def _version_from_descid(version, descid):
    """
    Combine ``git-describe`` parts in a :pep:`440` version with "local" part.

    :param: version:
        anythng after the project and ``'-v`'`` i,
        e.g it is ``1.7.4.post0``. ``foo-project-v1.7.4.post0-2-g79ceebf8``
    :param: descid:
        the part after the *pvtag* and the 1st dash('-'), which must not be empty,
        e.g it is ``2-g79ceebf8`` for ``foo-project-v1.7.4.post0-2-g79ceebf8``.
    :return:
        something like this: ``1.7.4.post0+2.g79ceebf8`` or ``1.7.4.post0``
    """
    assert descid, (version, descid)
    local_part = descid.replace('-', '.')
    return '%s+%s' % (version, local_part)


def _interp_fnmatch(tag_format, vprefix, pname):
    return tag_format.format(pname=pname,
                             version='*',
                             vprefix=vprefix)


def _interp_regex(tag_regex, vprefix, pname):
    return tag_regex.format(pname=pname,
                            vprefix=vprefix)


def _git_describe_parsed(pname,
                         default_version,        # if None, raise
                         tag_format, tag_regex,
                         vprefixes,
                         repo_path, git_options):
    """
    Parse git-desc as `pvtag, version, descid` or raise when no `default_version`.

    :param vprefixes:
        a sequence of str; no surprises, just make that many match-patterns
    """
    assert not isinstance(vprefixes, str), "req list-of-str, got: %r" % vprefixes

    import re

    if git_options:
        if isinstance(git_options, str):
            git_options = git_options.split()
        else:
            try:
                git_options = [str(s) for s in git_options]
            except Exception as ex:
                raise TypeError(
                    "invalid `git_options` due to: %s"
                    "\n  must be a str or an iterable, got: %r" %
                    (ex, git_options))
    tag_patterns, tag_regexes = zip(
        *((_interp_fnmatch(tag_format, vp, pname),
           re.compile(_interp_regex(tag_regex, vp, pname)))
          for vp in vprefixes))

    #
    ## Guard against git's runtime errors, below,
    #  and not configuration-ones, above.
    #
    pvtag = version = descid = None
    try:
        cmd = 'git describe'.split()
        if git_options:
            cmd.extend(git_options)
        cmd.extend('--match=' + tp for tp in tag_patterns)
        pvtag = _my_run(cmd, cwd=repo_path)
        matched_project, version, descid = split_pvtag(pvtag, tag_regexes)
        if matched_project and matched_project != pname:
            log.warning("Matched  pvtag project '%s' different from expected '%s'!",
                        matched_project, pname)
        if descid:
            version = _version_from_descid(version, descid)
    except:  # noqa:  E722
        if default_version is None:
            raise

    if not version:
        version = default_version

    return pvtag, version, descid


def polyversion(**kw):
    """
    Report the *pvtag* of the `pname` in the git repo hosting the source-file calling this.

    :param str pname:
        The project-name, used as the prefix of pvtags when searching them.
        If not given, defaults to the *last segment of the module-name of the caller*.

        .. Attention::
           when calling it from ``setup.py`` files, auto-deduction above
           will not work;  you must supply a project name.
    :param str default_version:
        What *version* to return if git cmd fails.
        Set it to `None` to raise if no *vtag* found.

        .. Tip::
           For cases where a shallow git-clone does not finds any *vtags*
           back in history, or simply because the project is new, and
           there are no *vtags*, we set default-version to empty-string,
           to facilitate pip-installing these projects from sources.

    :param bool mono_project:
      - false: (default) :term:`monorepo`, ie multiple sub-projects per git-repo.
        Tags formatted by *pvtags* :data:`pvtag_format` & :data:`pvtag_regex`
        (like ``pname-v1.2.3``).
      - true: :term:`mono-project`, ie only one project in git-repo
        Tags formatted as *vtags* :data:`vtag_format` & :data:`vtag_regex`.
        (like ``v1.2.3``).
    :param str tag_format:
        The :pep:`3101` pattern for creating *pvtags* (or *vtags*).

        - It receives 3 parameters to interpolate: ``{pname}, {vprefix}, {version} = '*'``.
        - It is used also to generate the match patterns for ``git describe --match <pattern>``
          command.
        - It overrides `mono_project` arg.
        - See :data:`pvtag_format` & :data:`vtag_format`
    :param regex tag_regex:
        The regex pattern breaking apart *pvtags*, with 3 named capturing groups:

        - ``pname``,
        - ``version`` (without the 'v'),
        - ``descid`` (optional) anything following the dash('-') after
          the version in ``git-describe`` result.

        - It is given 2 :pep:`3101` parameters ``{pname}, {vprefix}`` to interpolate.
        - It overrides `mono_project` arg.
        - See :pep:`0426` for project-name characters and format.
        - See :data:`pvtag_regex` & :data:`vtag_regex`
    :param str vprefixes:
        a 2-element array of str - :data:`tag_vprefixes` assumed when not specified
    :param is_release:
        used as boolean-index into :data:`tag_vprefixes`:

        - false: v-tags searched;
        - true: r-tags searched;
        - None: both tags searched.
    :param str repo_path:
        A path inside the git repo hosting the `pname` in question; if missing,
        derived from the calling stack
    :param git_options:
        a str or an iterator of (converted to str) options to pass
        to ``git describe`` command (empty by default).  If a string,
        it is splitted by spaces.
    :param return_all:
        when true, return the 3-tuple (tag, version, desc-id) (not just version)
    :return:
        The version-id (or 3-tuple) derived from the *pvtag*, or `default` if
        command failed/returned nothing, unless None, in which case, it raises.
    :raise sbp.CalledProcessError:
        if it cannot find any vtag and `default_version` is None
        (e.g. no git cmd/repo, no valid tags)

    .. Tip::
        It is to be used, for example, in package ``__init__.py`` files like this::

            __version__ = polyversion()

        Or from any other file::

            __version__ = polyversion('myproj')

    .. Note::
       This is a python==2.7 & python<3.6 safe function; there is also the similar
       function with elaborate error-handling :func:`polyvers.pvtags.describe_project()`
       in the full-blown tool `polyvers`.
    """
    pname = kw.get('pname')
    default_version = kw.get('default_version')
    repo_path = kw.get('repo_path')
    mono_project = kw.get('mono_project')
    tag_format = kw.get('tag_format')
    tag_regex = kw.get('tag_regex')
    vprefixes = kw.get('vprefixes')
    is_release = kw.get('is_release')
    git_options = kw.get('git_options')
    return_all = kw.get('return_all')

    if not pname:
        pname = _caller_module_name()

    if tag_format is None:
        tag_format = vtag_format if mono_project else pvtag_format
    if tag_regex is None:
        tag_regex = vtag_regex if mono_project else pvtag_regex
    if not repo_path:
        repo_path = _caller_fpath()
        if not repo_path:
            repo_path = '.'

    ## Decide `vprefix` (v-tag or r-tag).
    #
    if vprefixes is None:
        vprefixes = tag_vprefixes
    if len(vprefixes) != 2:
        raise ValueError(
            "Args 'vprefixes' in `polyversion()` must be a 2 element str-array"
            ", got: %r" % (vprefixes, ))
    if is_release is not None:
        vprefixes = (vprefixes[bool(is_release)], )

    tag, version, descid = _git_describe_parsed(pname, default_version,
                                                tag_format, tag_regex,
                                                vprefixes,
                                                repo_path, git_options)
    if return_all:
        return tag, version, descid
    return version


def polytime(**kw):
    """
    The timestamp of last commit in git repo hosting the source-file calling this.

    :param str no_raise:
        If true, never fail and return current-time
    :param str repo_path:
        A path inside the git repo hosting the project in question; if missing,
        derived from the calling stack.
    :return:
        the commit-date if in git repo, or now; :rfc:`2822` formatted
    """
    no_raise = kw.get('no_raise', False)
    repo_path = kw.get('repo_path')

    cdate = None
    if not repo_path:
        repo_path = _caller_fpath()
    cmd = "git log -n1 --format=format:%cD"
    try:
            cdate = _my_run(cmd, cwd=repo_path)
    except:  # noqa:  E722
        if not no_raise:
            raise

    if not cdate:
        cdate = rfc2822_tstamp()

    return cdate


__version__ = '0.1.0a3'
__updated__ = '2018-06-04T01:15:49.692836'


def run(*args):
    """
    Describe the version of a *polyvers* projects from git tags.

    USAGE:
        %(prog)s [-t] [PROJ-1] ...
        %(prog)s [-v | -V ]     # print my version information

    See http://polyvers.readthedocs.io

    :param argv:
        Cmd-line arguments, nothing assumed if nothing given.

    - Invokes :func:`polyversion.run()` with ``sys.argv[1:]``.
    - In order to set cmd-line arguments, invoke directly the function above.
    - With a single project, it raises any problems (e.g. no tags).
    """
    import os

    for o in ('-h', '--help'):

        if o in args:
            import textwrap as tw

            cmdname = osp.basename(sys.argv[0])
            doc = tw.dedent('\n'.join(run.__doc__.split('\n')[1:7]))
            print(doc % {'prog': cmdname})
            return

    if '-v' in args:
        print(__version__, end='')
        return
    if '-V' in args:
        print("version: %s\nupdated: %s\nfile: %s" % (
            __version__, __updated__, __file__))
        return

    print_tag = None
    if '-t' in args:
        print_tag = True
        args = list(args)
        del args[args.index('-t')]

    if len(args) == 1:
        res = polyversion(pname=args[0], repo_path=os.curdir,
                          return_all=print_tag)
        # fetces either 1-triplet or screams.
        if print_tag:
            res = res[0]

    else:
        versions = [(pname, polyversion(pname=pname,
                                        default_version='',
                                        repo_path=os.curdir,
                                        return_all=print_tag))
                    for pname in args]

        if print_tag:
            versions = [(pname, ver[0]) for pname, ver in versions]

        res = '\n'.join('%s: %s' % (pname, ver or '') for pname, ver in versions)

    if res:
        print(res)
