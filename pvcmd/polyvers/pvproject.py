#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2015-2018 European Commission (JRC);
# Licensed under the EUPL 1.2+ (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl
#
"""
The main structures of *polyvers*::

    Project 1-->* Engrave 1-->* Graft
"""
from pathlib import Path
from typing import List, Optional, Tuple, Match, Sequence, Union, Pattern
import logging
import re

import polyversion as pvlib
import textwrap as tw

from . import vermath
from ._vendor.traitlets import traitlets as trt
from ._vendor.traitlets.traitlets import (
    List as ListTrait, Tuple as TupleTrait, Union as UnionTrait)
from ._vendor.traitlets.traitlets import Bool, Unicode, Instance
from .cmdlet import cmdlets, autotrait
from .cmdlet.slicetrait import Slice as SliceTrait
from .utils import yamlutil as yu
from .utils.oscmd import cmd


log = logging.getLogger(__name__)


PatternClass = type(re.compile('.*'))  # For traitlets
MatchClass = type(re.match('.*', ''))  # For traitlets

FPaths = List[Path]
FLike = Union[str, Path]
FLikeList = Sequence[FLike]


def _slices_to_ids(slices, thelist):
    from boltons.setutils import IndexedSet as iset

    all_ids = list(range(len(thelist)))
    mask_ids = iset()
    for aslice in slices:
        mask_ids.update(all_ids[aslice])

    return list(mask_ids)


class Graft(cmdlets.Replaceable, cmdlets.Printable, yu.YAMLable, cmdlets.Spec):
    regex = Unicode(
        read_only=True,
        config=True,
        help="The regular-expressions to search within the byte-contents of files."
    )

    @trt.validate('regex')
    def _is_valid_regex(self, proposal):
        value = proposal.value
        try:
            v = self.interp(value,
                            _stub_keys=lambda k: '<%s>' % k,  # real values from project
                            _escaped_for='regex')
            re.compile(v.encode(self.encoding))
        except Exception as ex:
            proposal.trait.error(None, value, ex)
        return value

    def regex_resolved(self, project: 'Project') -> Pattern:
        v = project.interp(self.regex, _escaped_for='regex')
        return re.compile(v.encode(self.encoding))

    subst = Unicode(
        allow_none=True, default_value='',
        help="""
        What to replace with; if `None`, no substitution happens.

        Inside them, supported extensions are:
        - captured groups with '\\1 or '\g<foo>' expressions
          (see Python's regex documentation)
        - interpolation variables; Keys available (apart from env-vars prefixed with '$'):
          {ikeys}
        - WARN: put x2 all '{' and '}' chars like this: `\\w{{1,5}}` or else,
          interpolation will scream.
        """
    )

    def subst_resolved(self, project: 'Project') -> bytes:
        v = project.interp(self.subst)
        return v.encode(self.encoding)

    slices = UnionTrait(
        (SliceTrait(), ListTrait(SliceTrait())),
        read_only=True,
        config=True,
        help="""
        Which of the `hits` to substitute, in "slice" notation(s); all if not given.

        Example::

            gs = Graft()
            gs.slices = 0                ## Only the 1st match.
            gs.slices = '1:'             ## Everything except the 1st match
            gs.slices = ['1:3', '-1:']   ## Only 2nd, 3rd and the last match.
                "

        """
    )

    encoding = Unicode(
        'utf-8',
        config=True,
        help="""How to encode regex into bytes for matching file contents.""")

    def collect_matches(self, fbytes: bytes, project: 'Project') -> List[Match]:
        """
        :return:
            all `hits`; use :meth:`sliced_matches` to apply any slices
        """
        with self.errlogged(token='scan',
                            doing="scanning %s" % self):
            regex = self.regex_resolved(project)
            matches = list(regex.finditer(fbytes))

        return matches

    def sliced_matches(self, matches: List[Match]) -> List[Match]:
        slices = self.slices
        if not slices or not matches:
            return matches
        else:
            if not isinstance(slices, list):
                slices = [slices]

            match_indices = _slices_to_ids(slices, matches)
            return [matches[i] for i in match_indices]

    def substitute_matches(self,
                           fbytes: bytes,
                           matches: List[Match],
                           offset: int,
                           project: 'Project',
                           ) -> Tuple[bytes, int]:
        """
        :return:
            the substituted fbytes
        """
        if self.subst:
            subst = self.subst_resolved(project)
            for m in matches:
                if subst is not None:
                    with self.errlogged(token='subst',
                                        doing="substituting %s --> %s" %
                                        (subst, m)):
                        new_text = m.expand(subst)
                        head = fbytes[:m.start() + offset]
                        tail = fbytes[m.end() + offset:]
                        fbytes = head + new_text + tail
                        offset += len(new_text) - (m.end() - m.start())

        return fbytes, offset


class Engrave(cmdlets.Replaceable, cmdlets.Printable, yu.YAMLable, cmdlets.Spec):
    """File-patterns to search and replace with version-id patterns."""

    globs = ListTrait(
        Unicode(),
        read_only=True,
        config=True,
        help="A list of POSIX file patterns (.gitgnore-like) to search and replace"
    ).tag(printable=True)

    grafts = ListTrait(
        autotrait.AutoInstance(Graft),
        read_only=True,
        config=True,
        help="""
        A list of `Graft` for engraving (search & replace) version-ids or other infos.

        Use `{appname} config desc Graft` to see its syntax.
        """
    )


class Project(cmdlets.Replaceable, cmdlets.Printable, yu.YAMLable, cmdlets.Spec):
    pname = Unicode(
        config=True,
        help="""The name of the project, used in interpolations and pvtags, among others."""
    ).tag(printable=True)

    basepath = Instance(
        Path,
        default_value=None, allow_none=True,
        castable=str,
        config=True,
        help="""
        The root-dir of this project.

        - Usually this the folder where `setup.py` resides.
        - Projects may be nested but not exactly overlap.
        - Searched and substitutions for a project stop when reaching
          the basepath of other projects.
          """
    ).tag(printable=True)

    start_version_id = Unicode(
        '0.0.0',
        config=True,
        help="""If no pvtag found, use this as the base for relative versions.""")

    current_version = vermath.Pep440Version(
        None, allow_none=True,
        help="The previous version, auto-discovered.")

    release_date = Unicode(
        help="The automatic release date, to interpolate it.")

    @trt.default('release_date')
    def _get_now(self):
        from datetime import datetime

        return datetime.now().isoformat()

    ## TODO: rename version-->new_version
    version = vermath.Pep440Version(
        None, allow_none=True,
        help="The new absolute version to bump to.")

    amend = Bool(
        config=True,
        help="Amend the last version tag of the project, don't bump.")

    def load_current_version_from_history(self):
        vtag_index = -2 if self.amend else -1
        try:
            self.current_version = self.pvtags_history[vtag_index]
        except IndexError:
            self.log.debug("A vtag[%i] does not exist in history of %s",
                           vtag_index, self)
            self.current_version = self.start_version_id

    def set_new_version(self, version_bump: str = None):
        """
        :param version_bump:
            relative or absolute
        """
        if not version_bump:
            version_bump = self.default_version_bump

        if vermath._is_version_id_relative(version_bump):
            op, v2 = version_bump[0], version_bump[1:]
            self.version = vermath.calc_versions_op(op,
                                                    self.current_version,
                                                    v2)
        else:
            self.version = version_bump

    tag_vprefixes = TupleTrait(
        Unicode(), Unicode(),
        default_value=pvlib.tag_vprefixes,
        config=True,
        help="""
        A 2-tuple containing the ``{vprefix}`` interpolation values,
        one for *version-tags* and one for *release-tags*, respectively.
    """)

    pvtag_frmt = Unicode(
        help="""
        The pattern to generate new *pvtags*.

        It is interpolated with this class's traits as :pep:`3101` parameters;
        among others ``{pname}`` and ``{version}``; use ``{ikeys}`` to receive
        all available keys.

        .. WARNING::
           If you change this, ensure the :func:`polyversion.polyversion()`
           gets invoked from project's sources with the same value
           in `pvtag_frmt` kw-arg.
    """).tag(config=True)

    def _format_vtag(self, version, is_release=False):
        return self.interp(self.pvtag_frmt,
                           version=version,
                           vprefix=self.tag_vprefixes[int(is_release)])

    def tag_fnmatch(self, is_release=False):
        """
        The glob-pattern finding *pvtags* with ``git describe --match <pattern>`` cmd.

        :param is_release:
            `False` for version-tags, `True` for release-tags

        By default, it is interpolated with two :pep:`3101` parameters::

            {pname}   <-- this Project.pname
            {version} <-- '*'
        """
        vprefix = self.tag_vprefixes[int(is_release)]
        return self.interp(self.pvtag_frmt,
                           vprefix=vprefix,
                           version='*',
                           _escaped_for='glob')

    pvtag_regex = Unicode(
        help="""
        The regex pattern breaking *pvtags* and/or ``git-describe`` output
        into 3 named capturing groups:
        - ``pname``,
        - ``version`` (without the 'v'),
        - ``descid`` (optional) anything following the dash('-') after
          the version in ``git-describe`` result.

        It is interpolated with this class's traits as :pep:`3101` parameters;
        among others ``{pname}``, and **maybe** ``{version}``; use ``{ikeys}``
        to receive all available keys.
        See :pep:`0426` for project-name characters and format.

        .. WARNING::
           If you change this, ensure the :func:`polyversion.polyversion()`
           gets invoked from project's sources with the same value
           in `pvtag_regex` kw-arg.
    """).tag(config=True)

    @trt.validate('pvtag_regex')
    def _is_valid_pvtag_regex(self, proposal):
        value = proposal.value
        try:
            for vprefix in self.tag_vprefixes:
                v = self.interpolations.interp(
                    value,
                    pname='<pname>', vprefix=vprefix)
                re.compile(v)
        except Exception as ex:
            proposal.trait.error(None, value, ex)
        return value

    tag = Bool(
        config=True,
        help="""
        Enable tagging, per-project.

        Adds a signed tag with name/msg from `tag_name`/`message` (commit implied).

        """)

    message_summary = Unicode(
        "{pname}-{current_version} -> {version}",
        config=True,
        help="""
            The commit & tag message's summary-line part for this project.

            Available interpolations (apart from env-vars prefixed with '$'):
            {ikeys}
        """)

    message_body = Unicode(
        config=True,
        help="""
            The commit & tag message-body part for this project.

            Available interpolations (apart from env-vars prefixed with '$'):
            {ikeys}
        """)

    def tag_regex(self, is_release=False) -> Pattern:
        """
        Interpolate and compile as regex.

        :param is_release:
            `False` for version-tags, `True` for release-tags
        """
        vprefix = self.tag_vprefixes[int(is_release)]
        regex = self.interp(self.pvtag_regex,
                            vprefix=vprefix,
                            _escaped_for='regex')
        return re.compile(regex)

    _pvtags_collected = ListTrait(
        Unicode(), allow_none=True, default_value=None,
        help="Populated internally by `populate_pvtags_history()`.")

    @property
    def pvtags_history(self) -> List[str]:
        """
        Return the full *pvtag* history for the project, if any.

        :raise AssertionError:
           If used before :func:`populate_pvtags_history()` applied on this project.
        """
        if self._pvtags_collected is None:
            raise AssertionError("Call first `populate_pvtags_history()` on %s!")
        return self._pvtags_collected

    def version_from_pvtag(self, pvtag: str) -> Optional[str]:
        """Extract the version from a *pvtag*."""
        m = self.tag_regex().match(pvtag)
        if m:
            mg = m.groupdict()

            return mg['version']

    def git_describe(self, *git_args: str,
                     include_lightweight=False,
                     is_release=False,
                     **git_flags: str):
        """
        Gets sub-project's version as derived from ``git describe`` on its *pvtag*.

        :param include_lightweight:
            Consider also non-annotated tags when derriving description;
            equivalent to ``git describe --tags`` flag.
        :param is_release:
            `False` for version-tags, `True` for release-tags
        :param git_args:
            CLI options passed to ``git describe`` command.
            See :class:`.oscmd.PopenCmd` on how to specify cli options
            using python functions, e.g. ``('*-v*', '*-r*')``
        :param git_flags:
            CLI flags passed to ``git describe`` command.
            - See :class:`.oscmd.PopenCmd` on how to specify cli flags
              using python functions, e.g. ``(all=True)``.
            - See https://git-scm.com/docs/git-describe
        :return:
            the *pvtag* of the current project, or raise
        :raise GitVoidError:
            if sub-project is not *pvtagged*.
        :raise NoGitRepoError:
            if CWD not within a git repo.
        :raise sbp.CalledProcessError:
            for any other error while executing *git*.

        .. NOTE::
           There is also the python==2.7 & python<3.6 safe :func:`polyvers.polyversion()``
           for extracting just the version part from a *pvtag*; use this one
           from within project sources.

        .. INFO::
           Same results can be retrieved by this `git` command::

               git describe --tags --match <PROJECT>-v*

           where ``--tags`` is needed to consider also non-annotated tags,
           as ``git tag`` does.
        """
        from .import pvtags

        tag_pattern = self.tag_fnmatch(is_release)

        ## TODO: move to pvtags
        acli = cmd.git.describe
        if include_lightweight:
            acli._(tags=True)

        with pvtags.git_project_errors_handled(self.pname):
            out = acli._(*git_args, **git_flags)(match=tag_pattern)

        version = out

        ## `git describe --all` fetches 'tags/` prefix.
        if 'all' in git_flags:
            version = version.lstrip('tags/')

        if not self.version_from_pvtag(version):
            raise trt.TraitError(
                "Project-version '%s' fetched by '%s' unparsable by regex: %s"
                % (version, tag_pattern, self.tag_regex().pattern))

        return version

    def last_commit_tstamp(self):
        """
        Report the timestamp of the last commit of the git repo.

        :return:
            last commit's timestamp in :rfc:`2822` format

        :raise GitVoidError:
            if there arn't any commits yet or CWD not within a git repo.
        :raise sbp.CalledProcessError:
            for any other error while executing *git*.

        .. INFO::
           Same results can be retrieved by this `git` command::

               git describe --tags --match <PROJECT>-v*

           where ``--tags`` is needed to consider also unannotated tags,
           as ``git tag`` does.
        """
        from .import pvtags

        with pvtags.git_project_errors_handled(self.pname):
            out = cmd.git.log(n=1, format='format:%cD')  # TODO: traitize log-date format

        return out

    def tag_version_commit(self, bump_cmd, is_release=False):
        """
        Make a tag on current commit denoting a version-bump.

        :param is_release:
            `False` for version-tags, `True` for release-tags
        """
        import subprocess as sbp
        from . import pvtags

        tag_name = self._format_vtag(self.version, is_release)
        msg = bump_cmd._make_commit_message(self)
        ## TODO: move all git-cmds to pvtags?
        try:
            cmd.git.tag(tag_name,
                        message=msg,
                        force=self.is_forced('tag') or None,
                        sign=bump_cmd.sign_tags or None,
                        local_user=bump_cmd.sign_user or None,
                        )
        except sbp.CalledProcessError as ex:
            if "already exists" in str(ex.stderr):
                raise pvtags.GitError(
                    "Cannot bump, tag '%s' already exists!"
                    "\n  Add `--force=tag` if you must." % tag_name)
            raise

    engraves = ListTrait(
        autotrait.AutoInstance(Engrave),
        default_value=[{
            'globs': ['setup.py'],
            'grafts': [{
                ## TODO: add `Graft.desc` field
                ## version must be in its own line.
                'regex': tw.dedent(r'''
                    (?xm)
                        \bversion
                        (\ *=\ *)
                        .+?(,
                        \ *[\n\r])+
                    '''),
                'subst': r"version\1'{version}'\2"
            }],
        }, {
            'globs': ['__init__.py'],
            'grafts': [{
                'regex': tw.dedent(r'''
                    (?xm)
                        \b__version__
                        (\ *=\ *)
                        (.+[\r\n])
                    '''),
                'subst': r"__version__\1'{version}'"
            }, {
                'regex': tw.dedent(r'''
                    (?xm)
                        \b__updated__
                        (\ *=\ *)
                        (.+[\r\n])
                    '''),
                'subst': r"__updated__\1'{release_date}'"
            }],
        }, {
            'globs': ['README.rst'],
            'grafts': [{
                'regex': r'\|version\|',
                'subst': "{version}"
            }, {
                'regex': r'\|today\|',
                'subst': "{release_date}"
            }],
        }],
        config=True,
        help="""
        """)

    default_version_bump = Unicode(
        '^1',
        config=True,
        help="Which relative version to imply if not given in the cmd-line."
    )

    @trt.validate('default_version_bump')
    def _require_relative_version(self, change):
        if not vermath._is_version_id_relative(change.new):
            raise trt.TraitError(
                "Expected a relative version for '%s.%s', but got '%s'!"
                "\n  Relative versions start either with '+' or '^'." %
                change.owner, change.trait.name, change.new)
