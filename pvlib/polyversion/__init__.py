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
import os
import sys

import os.path as osp
import subprocess as sbp


__all__ = 'polyversion polytime decide_vprefixes'.split()


PY2 = sys.version_info < (3, )
PY_OLD_SBP = sys.version_info < (3, 5)
log = logging.getLogger(__name__)
_log_stack = {} if PY2 else {'stack_info': True}


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


if PY_OLD_SBP:
    from subprocess import CalledProcessError
else:
    class CalledProcessError(sbp.CalledProcessError):
        """
        "A :class:`sbp.CalledProcessError` that includes STDOUT/STDERR on its message.
        """
        def __init__(self, returncode, cmd, output=None, stderr=None, cwd=None):
            try:
                super(CalledProcessError, self).__init__(returncode, cmd, output, stderr)
                self.cwd = cwd
            except TypeError:
                ## In PY < 3.5 Ex has no output/stderr attributes.
                super(CalledProcessError, self).__init__(returncode, cmd)
                self.output = self.stdout == output
                self.stderr = stderr

        def __str__(self):
            out = getattr(self, 'stdout', None)  # strangely not always there...
            err = getattr(self, 'stderr', None)
            cwd = getattr(self, 'cwd', None)
            tail = ('\n  STDERR: %s' % err) if err else ''
            tail += ('\n  STDOUT: %s' % out) if out else ''
            tail += ('\n     CWD: %s' % cwd) if cwd else ''

            err = super(CalledProcessError, self).__str__()

            return err + tail


def _my_run(cmd, cwd):
    "For commands with small output/stderr."
    if not isinstance(cmd, (list, tuple)):
        cmd = cmd.split()
    proc = sbp.Popen(cmd, stdout=sbp.PIPE, stderr=sbp.PIPE,
                     cwd=str(cwd), bufsize=-1)
    out, err = proc.communicate()

    if proc.returncode != 0:
        streams = () if PY_OLD_SBP else [out, err, cwd]
        raise CalledProcessError(proc.returncode, cmd, *streams)
    else:
        return _clean_cmd_result(out)


def pkg_metadata_version(pname, basepath=None):
    """Get the version from package metadata if present.

    :param pname:
        package-name
    :param basepath:
        The path of the outermost package inside the git repo hosting the project
        if missing, cwd assumed.

    :return:
      `None` if nothing found

    It will retrieve the version from these ``<basepath>`` filepaths (see :pep:`0376`),
    and in this order:

      - ``../<pname>-<version>.dist-info/METADATA``: for packages
        installed in PYTHONPATH from a *wheel*.
      - ``../<pname>-<version>.egg-info/PKG-INFO``: for packages
        installed in PYTHONPATH from an *(bdist) egg*.
      - ``METADATA``: when launched from within for *wheels*.
      - ``PKG-INFO``: when launched from within for *sdists*,
    """
    import email
    import glob

    pkg_metadata_fpaths = [
        osp.join('..', '%s-*.dist-info' % pname, 'METADATA'),  # wheel
        osp.join('..', '%s-*.egg-info' % pname, 'PKG-INFO'),   # egg
        'METADATA',
        'PKG-INFO',
    ]
    pkg_metadata = {}
    for fpath in pkg_metadata_fpaths:
        fpath = osp.join(str(basepath) or '.', fpath)
        try:
            matches = glob.glob(fpath)
            if len(matches) == 1:
                fpath = matches[0]
            else:
                if len(matches) > 1:
                    log.warning("Many matches while searching version in '%s': %s",
                                osp.realpath(fpath), matches)
                continue

            pkg_metadata_file = open(fpath, 'r',
                                     encoding='utf-8',
                                     errors='ignore')
        except (IOError, OSError) as ex:
            log.warning("Ignored error while searching version in '%s': %s",
                        osp.realpath(fpath), ex)
            continue
        try:
            pkg_metadata = email.message_from_file(pkg_metadata_file)
        except email.errors.MessageError as ex:
            log.warning("Ignored error while searching version in '%s': %s",
                        osp.realpath(fpath), ex)
            continue

    # Check to make sure we're in our own dir
    meta_pname = pkg_metadata.get('Name', None)
    if meta_pname == pname:
        return pkg_metadata.get('Version', None)
    elif meta_pname is not None:
        log.warning("Skipping version '%s' from foreign project '%s' (expecting '%s').",
                    pkg_metadata.get('Version', None), meta_pname, pname)


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


def _caller_basepath(nframes_back=2):
    import inspect

    frame = inspect.currentframe()
    try:
        for _ in range(nframes_back):
            frame = frame.f_back
        mod = inspect.getmodule(frame)

        topackage = __import__(mod.__name__.split('.')[0])
        basepath = osp.dirname(inspect.getfile(topackage))

        return basepath
    finally:
        del frame


def split_pvtag(pvtag, tag_regexes):
    ## TODO: parse descids like `setuptools_scm` plugin:
    #  https://pypi.org/project/setuptools_scm/#default-versioning-scheme
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
            raise ValueError("Matching pvtag '%s' by '%s' failed due to: %s",
                             pvtag, tregex.pattern, ex)

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
                         basepath, git_options):
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
        ## FIXME: buggy git < 2.15.0 ignores multiple match-patterns but the last
        cmd.extend('--match=' + tp for tp in tag_patterns)
        pvtag = _my_run(cmd, cwd=basepath)
        matched_project, version, descid = split_pvtag(pvtag, tag_regexes)
        if matched_project and matched_project != pname:
            log.warning("Matched  pvtag project '%s' different from expected '%s'!",
                        matched_project, pname)
        if descid:
            version = _version_from_descid(version, descid)
    except Exception as ex:
        if default_version is None:
            raise
        else:
            log.warning(
                "polyversion(): falling back to default-version '%s' "
                "due to ignored error: %s",
                default_version, ex, **_log_stack)

    if not version:
        version = default_version

    return pvtag, version, descid


def decide_vprefixes(vprefixes, is_release):
    "Decide v-tag, r-tag or both; no surprises params, return always an array."

    if vprefixes is None:
        vprefixes = tag_vprefixes
    if len(vprefixes) != 2:
        raise ValueError(
            "Args 'vprefixes' in `polyversion()` must be a 2 element str-array"
            ", got: %r" % (vprefixes, ))
    if is_release is not None:
        vprefixes = (vprefixes[bool(is_release)], )

    return vprefixes


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
    :param str default_version_env_var:
        Override which env-var to read *version* from, if git cmd fails
        [Default: ``<pname>_VERSION``]
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
        a 3-state boolean used as index into :data:`tag_vprefixes`:

        - false: v-tags searched;
        - true: r-tags searched;
        - None: both tags searched.
    :param str basepath:
        The path of the outermost package inside the git repo hosting the project;
        if missing, assumed as the dirname of the calling code's package.
    :param git_options:
        a str or an iterator of (converted to str) options to pass
        to ``git describe`` command (empty by default).  If a string,
        it is splitted by spaces.
    :param return_all:
        when true, return the 3-tuple (tag, version, desc-id) (not just version)

    :return:
        The version-id (or 3-tuple) derived from the *pvtag*, or `default` if
        command failed/returned nothing, unless None, in which case, it raises.
    :raise CalledProcessError:
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
    basepath = kw.get('basepath')
    mono_project = kw.get('mono_project')
    tag_format = kw.get('tag_format')
    tag_regex = kw.get('tag_regex')
    vprefixes = kw.get('vprefixes')
    is_release = kw.get('is_release')
    git_options = kw.get('git_options')
    return_all = kw.get('return_all')

    if not pname:
        pname = _caller_module_name()

    if not basepath:
        basepath = _caller_basepath()
        if not basepath:
            basepath = '.'

    version = pkg_metadata_version(pname, basepath)
    if version:
        if return_all:
            return None, version, None
        return version

    if not default_version:
        defver_envvar = kw.get('default_version_env_var', '%s_VERSION' % pname)
        ## Ignore empty/none envvars
        #  to preserve empty (but not none) `default-version` kwd.
        #
        env_ver = os.environ.get(defver_envvar)
        if env_ver:
            default_version = env_ver

    if tag_format is None:
        tag_format = vtag_format if mono_project else pvtag_format
    if tag_regex is None:
        tag_regex = vtag_regex if mono_project else pvtag_regex

    vprefixes = decide_vprefixes(vprefixes, is_release)
    tag, version, descid = _git_describe_parsed(pname, default_version,
                                                tag_format, tag_regex,
                                                vprefixes,
                                                basepath, git_options)
    if return_all:
        return tag, version, descid
    return version


def polytime(**kw):
    """
    The timestamp of last commit in git repo hosting the source-file calling this.

    :param str no_raise:
        If true, never fail and return current-time.
        Assumed true if a :term:`default version env-var` is found.
    :param str basepath:
        The path of the outermost package inside the git repo hosting the project;
        if missing, assumed as the dirname of the calling code's package.
    :param str pname:
        The project-name used only as the prefix for :term:`default version env-var`.
        If not given, defaults to the *last segment of the module-name of the caller*.
        Another alternative is to use directly the `default_version_env_var` kwd.

        .. Attention::
           when calling it from ``setup.py`` files, auto-deduction above
           will not work;  you must supply a project name.
    :param str default_version_env_var:
        Override which env-var to read *version* from, if git cmd fails
        [Default: ``<pname>_VERSION``]

    :return:
        the commit-date if in git repo, or now; :rfc:`2822` formatted
    """
    no_raise = kw.get('no_raise', False)
    basepath = kw.get('basepath')
    pname = kw.get('pname')

    if not pname:
        pname = _caller_module_name()

    if not basepath:
        basepath = _caller_basepath()

    cdate = None
    if not pkg_metadata_version(pname, basepath):
        defver_envvar = kw.get('default_version_env_var', '%s_VERSION' % pname)
        if os.environ.get(defver_envvar):
            no_raise = True

        cmd = "git log -n1 --format=format:%cD"
        try:
                cdate = _my_run(cmd, cwd=basepath)
        except Exception as ex:
            if not no_raise:
                raise
            else:
                log.warning(
                    "polytime(): falling back to current-time "
                    "due to ignored error: %s",
                    ex, **_log_stack)

    if not cdate:
        cdate = rfc2822_tstamp()

    return cdate


def _init_logging():
    level = os.environ.get('POLYVERSION_LOG_LEVEL')
    if level:
        try:
            level = int(level)
        except ValueError:
            pass
    else:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


## Initialize logging before my own version-setting.
#
if 'POLYVERSION_LOG_LEVEL' in os.environ:
    _init_logging()

__version__ = '0.2.1a0'
__updated__ = '2018-07-05T11:41:47.848168'


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
    - Use env-var[POLYVERSION_LOG_LEVEL] to control verbosity
      (0: show all, 10: DEBUG, 30: INFO, 40: WARN, 50: ERROR, 60=FATAL).
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

    _init_logging()

    if _log_stack:
        ## Not in PY2, and not really needed from main.
        _log_stack['stack_info'] = False

    if len(args) == 1:
        res = polyversion(pname=args[0], basepath=os.curdir,
                          return_all=print_tag)
        # fetces either 1-triplet or screams.
        if print_tag:
            res = res[0]

    else:
        versions = [(pname, polyversion(pname=pname,
                                        default_version='',
                                        basepath=os.curdir,
                                        return_all=print_tag))
                    for pname in args]

        if print_tag:
            versions = [(pname, ver[0]) for pname, ver in versions]

        res = '\n'.join('%s: %s' % (pname, ver or '') for pname, ver in versions)

    if res:
        print(res)
