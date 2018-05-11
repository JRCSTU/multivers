# -*- coding: utf-8 -*-
#
# Copyright 2015-2018 European Commission (JRC);
# Licensed under the EUPL 1.2+ (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl
#
"""The command that actually bumps versions."""
from typing import Sequence
from typing import Tuple, Set, List  # noqa: F401 @UnusedImport, flake8 blind in funcs

from boltons.setutils import IndexedSet as iset

from . import pvtags, pvproject, cli
from ._vendor.traitlets.traitlets import Bool, Unicode
from .cmdlet import cmdlets
from .utils.oscmd import cmd


class BumpCmd(cli._SubCmd):
    """
    Increase or set the version of project(s) to the (relative/absolute) version.

    SYNTAX:
        {cmd_chain} [OPTIONS] [<version>] [<project>]...

    - A version specifier, either ABSOLUTE, or RELATIVE to current version:

      - *ABSOLUTE* PEP-440 version samples:
        - Pre-releases: when working on new features:
            X.YbN               # Beta release
            X.YrcN  or  X.YcN   # Release Candidate
            X.Y                 # Final release
        - Post-release:
            X.YaN.postM         # Post-release of an alpha release
            X.YrcN.postM        # Post-release of a release candidate
        - Dev-release:
            X.YaN.devM          # Developmental release of an alpha release
            X.Y.postN.devM      # Developmental release of a post-release

      - *RELATIVE* samples:
        - +0.1          # For instance:
                        #   1.2.3    --> 1.3.0
        - ^2            # Increases the last non-zero part of current version:
                        #   1.2.3    --> 1.2.5
                        #   0.1.0b0  --> 0.1.0b2

    - If no <version> specified, '^1' assumed.
    - If no project(s) specified, increase the versions on all projects.
    - Denied if version for some projects is backward-in-time (or has jumped parts?);
      use --force if you might.
    - The 'v' prefix is not needed!
    """
    classes = [pvproject.Project, pvproject.Engrave, pvproject.Graft]  # type: ignore

    out_of_trunk_releases = Bool(
        True,
        config=True,
        help="""
            Version-ids statically engraved in-trunk when true, otherwise in "leaf" commits.

            - Limit branches considered as "in-trunk" using `in_trunk_branches` param.
            - Select the name of the Leaf branch with `leaf_branch` param.

            Leaf release-commits avoid frequent merge-conflicts in files containing
            the version-ids.
    """)

    release_branch = Unicode(
        'latest',
        config=True,
        help="""
        Branch-name where the release-tags must be created under.

        - The branch will be hard-reset to the *out-of-trunk* commit
          on each bump-version.
        - If not given, no special branch used for *rtags*.
        """
    )

    commit = Bool(
        config=True,
        help="""
            Commit after engraving with a commit-message describing version bump.

            - If false, no commit created, just search'n replace version-ids.
              Related params: out_of_trunk, message.
            - False make sense only if `use_leaf_releases=False`
        """)

    message_summary = Unicode(
        "chore(ver): bump {sub_summary}",
        config=True,
        help="""
            The commit & tag message's summary-line.

            - Additional interpolation: `sub_summary`
            - Others interpolations (apart from env-vars prefixed with '$'):
              {ikeys}
        """)

    message_body = Unicode(
        "{sub_body}",
        config=True,
        help="""
            The commit & tag message's body.

            - Additional interpolation: `sub_body`
            - Others interpolations (apart from env-vars prefixed with '$'):
              {ikeys}
        """)

    sign_tags = Bool(
        allow_none=True,
        config=True,
        help="Enable PGP-signing of tags (see also `sign_user`)."
    )

    sign_commmits = Bool(
        allow_none=True,
        config=True,
        help="Enable PGP-signing of *rtag* commits (see also `sign_user`)."
    )

    sign_user = Unicode(
        allow_none=True,
        config=True,
        help="The signing PGP user identity (email, key-id)."
    )

    def _stop_if_git_dirty(self):
        """
        Note: ``git diff-index --quiet HEAD --``
        from https://stackoverflow.com/a/2659808/548792
        give false positives!
        """
        ## TODO: move all git-cmds to pvtags?
        out = cmd.git.describe(dirty=True, all=True)
        if out.endswith('dirty'):
            raise pvtags.GitError("Dirty working directory, bump aborted.")

    def _filter_projects_by_pnames(self, projects, version, *pnames):
        """Separate `version` from `pnames`, scream if unknown pnames."""
        if pnames:
            all_pnames = [prj.pname for prj in projects]
            pnames = iset(pnames)
            unknown_projects = (pnames - iset(all_pnames))
            if unknown_projects:
                raise cmdlets.CmdException(
                    "Unknown project(s): %s\n  Choose from existing one(s): %s" %
                    (', '.join(unknown_projects), ', '.join(all_pnames)))

            projects = [p for p in projects
                        if p.pname in pnames]

        return version, projects

    def _make_commit_message(self, *projects: pvproject.Project):
        from ipython_genutils.text import indent, wrap_paragraphs

        sub_summary = ', '.join(prj.interp(prj.message_summary)  # type: ignore (null item)
                                for prj in projects)
        summary = self.interp(self.message_summary, sub_summary=sub_summary)

        text_lines: List[str] = []
        for prj in projects:
            if prj.message_body:
                text_lines.append('- %s' % prj.pname)
                text_lines.append(indent(wrap_paragraphs(prj.message_body), 2))

        sub_body = '\n'.join(text_lines).strip()
        body = self.interp(self.message_body, sub_body=sub_body)

        return '%s\n\n%s' % (summary, body)

    def _commit_new_release(self, projects: Sequence[pvproject.Project]):
        msg = self._make_commit_message(*projects)
        ## TODO: move all git-cmds to pvtags?
        out = cmd.git.commit(message=msg,  # --message=fo bar FAILS!
                             all=True,
                             sign=self.sign_commmits or None,
                             dry_run=self.dry_run or None,
                             )
        if self.dry_run:
            self.log.warning('PRETEND commit: %s' % out)

    def run(self, *version_and_pnames):
        from . import engrave

        projects = self.bootstrapp_projects()
        if version_and_pnames:
            version_bump, projects = self._filter_projects_by_pnames(projects, *version_and_pnames)
        else:
            version_bump = None

        pvtags.populate_pvtags_history(*projects)

        for prj in projects:
            ## Scream if version-bump fails pep440 validation.
            #
            prj.load_current_version_from_history()
            prj.set_new_version(version_bump)

        fproc = engrave.FileProcessor(parent=self)
        match_map = fproc.scan_projects(projects)
        if fproc.nmatches() == 0:
            raise cmdlets.CmdException(
                "No version-engraving matched, bump aborted.")

        ## Finally stop before serious damage happens,
        #  (but only after havin run some validation to run, above).
        self._stop_if_git_dirty()

        with pvtags.git_restore_point(restore=self.dry_run):
            fproc.engrave_matches(match_map)

            ## TODO: move all git-cmds to pvtags?
            if self.out_of_trunk_releases:
                for proj in projects:
                    proj.tag_version_commit(self, is_release=False)
                ## TODO: append new tags to git-restore-point.__exit__

                with pvtags.git_restore_point(restore=True):
                    if self.release_branch:
                        cmd.git.checkout._(B=True)(self.release_branch)
                    else:
                        cmd.git.checkout('HEAD')

                    self._commit_new_release(projects)

                    for proj in projects:
                        proj.tag_version_commit(self, is_release=True)
                    ## TODO: append new tags to git-restore-point.__exit__ if dry-run

            else:  # In-trunk plain *vtags* for mono-project repos.
                self._commit_new_release(projects)

                for proj in projects:
                    proj.tag_version_commit(self, is_release=False)
                ## TODO: append new tags to git-restore-point.__exit__

        self.log.notice('Bumped projects: %s',
                        ', '.join('%s-%s --> %s' %
                                  (prj.pname, prj.current_version, prj.version)
                                  for prj in projects))

    def start(self):
        with self.errlogged(doing="running cmd '%s'" % self.name,
                            info_log=self.log.info):
            return super().start()


BumpCmd.flags = {  # type: ignore
    ('c', 'commit'): (
        {'BumpCmd': {'commit': True}},
        BumpCmd.commit.help
    ),
    ('s', 'sign-tags'): (
        {'BumpCmd': {'sign_tags': True}},
        BumpCmd.sign_tags.help
    ),
    ('a', 'amend'): (
        {'pvproject.Project': {'amend': True}},
        pvproject.Project.amend.help
    ),
    ('t', 'tag'): (
        {'Project': {'tag': True}},
        pvproject.Project.tag.help
    ),
}
BumpCmd.aliases = {  # type: ignore
    ('m', 'message'): 'BumpCmd.message_body',
    ('i', 'sign-user'): 'BumpCmd.sign_user',
}
