# -*- coding: utf-8 -*-
#
# Copyright 2015-2018 European Commission (JRC);
# Licensed under the EUPL 1.2+ (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl
#
"""The code of *polyvers* shell-commands."""

from collections import OrderedDict, defaultdict
import io
import logging

from . import APPNAME, __version__, __updated__, cmdlets, pvtags, fileutils as fu
from ._vendor import traitlets as trt
from ._vendor.traitlets import config as trc
from ._vendor.traitlets.traitlets import List, Bool, Unicode
from .autoinstance_traitlet import AutoInstance


log = logging.getLogger(__name__)

#: YAML dumper used to serialize command's outputs.
_Y = None


def ydumps(obj):
    "Dump any false objects as empty string, None as nothing, or as YAML. "
    global _Y

    if not _Y:
        from ruamel import yaml
        from ruamel.yaml.representer import RoundTripRepresenter

        for d in [OrderedDict, defaultdict]:
            RoundTripRepresenter.add_representer(
                d, RoundTripRepresenter.represent_dict)
        _Y = yaml.YAML()

    if obj is None:
        return
    if not obj:
        return ''

    sio = io.StringIO()
    _Y.dump(obj, sio)
    return sio.getvalue().strip()


####################
## Config sources ##
####################
CONFIG_VAR_NAME = '%s_CONFIG_PATHS' % APPNAME
#######################


class PolyversCmd(cmdlets.Cmd):
    """
    Bump independently PEP-440 versions of sub-project in Git monorepos.

    SYNTAX:
      {cmd_chain} <sub-cmd> ...
    """
    version = __version__
    examples = Unicode("""
        - Let it guess the configurations for your monorepo::
              {cmd_chain} init
          You may specify different configurations paths with:
              {cmd_chain} --config-paths /foo/bar/:~/.%(appname)s.yaml:.

        - Use then the main sub-commands::
              {cmd_chain} status
              {cmd_chain} setver 0.0.0.dev0 -c '1st commit, untagged'
              {cmd_chain} bump -t 'Mostly model changes, tagged'

        PEP-440 Version Samples:
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
    """)
    classes = [pvtags.Project]

    #: Interrogated by all Project instances by searching up their parent chain.
    default_project = AutoInstance(
        pvtags.Project,
        allow_none=True,
        config=True,
        help="""
        Set version-schema (monorepo/monoproject) by enforcing defaults for all Project instances.

        Installed by configuration, or auto-detected when no configs loaded.
        """)

    projects = List(
        AutoInstance(pvtags.Project),
        config=True)

    use_leaf_releases = Bool(
        True,
        config=True,
        help="""
            Version-ids statically engraved in-trunk when false, otherwise in "leaf" commits.

            - Limit branches considered as "in-trunk" using `in_trunk_branches` param.
            - Select the name of the Leaf branch with `leaf_branch` param.

            Leaf release-commits avoid frequent merge-conflicts in files containing
            the version-ids.
    """)

    amend = Bool(
        config=True,
        help="Amend the last bump-version commit, if any.")

    commit = Bool(
        config=True,
        help="""
            Commit after engraving with a commit-message describing version bump.

            - If false, no commit created, just search'n replace version-ids.
              Related params: out_of_trunk, message.
            - False make sense only if `use_leaf_releases=False`
        """)

    @trt.default('subcommands')
    def _subcommands(self):
        subcmds = cmdlets.build_sub_cmds(InitCmd, StatusCmd,
                                         BumpCmd,
                                         LogconfCmd)
        subcmds['config'] = (
            'polyvers.cfgcmd.ConfigCmd',
            "Commands to inspect configurations and other cli infos.")

        return subcmds

    def _my_text_interpolations(self):
        d = super()._my_text_interpolations()
        d.update({'appname': APPNAME})
        return d

    @trt.default('all_app_configurables')
    def _all_app_configurables(self):
        from . import engrave
        return [type(self),
                pvtags.Project,
                InitCmd, StatusCmd, BumpCmd, LogconfCmd,
                engrave.Engrave, engrave.GraftSpec,
                ]

    @trt.default('config_paths')
    def _config_paths(self):
        basename = self.config_basename
        paths = []

        git_root = fu.find_git_root()
        if git_root:
            paths.append(str(git_root / basename))
        else:
            paths.append('.')

        paths.append('~/%s' % basename)

        return paths

    def collect_app_infos(self):
        """Provide extra infos to `config infos` subcommand."""
        return {
            'version': __version__,
            'updated': __updated__,
            ## TODO: add more app-infos.
        }


class VersionSubcmd(PolyversCmd):
    def check_project_configs_exist(self, scream=True):
        """
        Checks if any loaded config-file is a subdir of Git repo.

        :raise CmdException:
            if cwd not inside a git repo
        """
        from pathlib import Path as P

        git_root = fu.find_git_root()
        if not git_root:
            raise cmdlets.CmdException(
                "Current-dir '%s' is not inside a git-repo!" % P().resolve())

        for p in self._cfgfiles_registry.collected_paths:
            try:
                if P(p).relative_to(git_root):
                    return True
            except ValueError as _:
                pass

        if scream:
            self.log.warning(
                "No '%s' config-file(s) found!\n"
                "  Invoke `polyvers init` to stop this warning.",
                git_root / self.config_basename)

        return False


class InitCmd(VersionSubcmd):
    """Generate configurations based on directory contents."""

    def run(self, *args):
        if len(args) > 0:
            raise cmdlets.CmdException(
                "Cmd %r takes no arguments, received %d: %r!"
                % (self.name, len(args), args))

        if not self.force and self.check_project_configs_exist(scream=False):
            raise cmdlets.CmdException(
                "Polyvers already initialized!"
                "\n  Use --force if you must, and also check those files:"
                "\n    %s" %
                '\n    '.join(self._cfgfiles_registry.collected_paths))

        yield "Init would be created...."


class StatusCmd(VersionSubcmd):
    """
    List the versions of project(s).

    SYNTAX:
        {cmd_chain} [OPTIONS] [<project>]...
    """
    def run(self, *args):
        self.check_project_configs_exist()


class BumpCmd(VersionSubcmd):
    """
    Increase the version of project(s) by the given offset.

    SYNTAX:
        {cmd_chain} [OPTIONS] [<version-offset>] [<project>]...
        {cmd_chain} [OPTIONS] --part <offset> [<project>]...

    - If no <version-offset> specified, increase the last part (e.g 0.0.dev0-->dev1).
    - If no project(s) specified, increase the versions for all projects.
    - Denied if version for some projects is backward-in-time or has jumped parts;
      use --force if you might.
    - Don't add a 'v' prefix!
    """
    def run(self, *args):
        self.check_project_configs_exist()


class LogconfCmd(PolyversCmd):
    """Write a logging-configuration file that can filter logs selectively."""
    def run(self, *args):
        pass


# TODO: Will work when patched: https://github.com/ipython/traitlets/pull/449
PolyversCmd.config_paths.tag(envvar=CONFIG_VAR_NAME)
trc.Application.raise_config_file_errors.tag(config=True)
trc.Application.raise_config_file_errors.help = \
    'Whether failing to load config files should prevent startup.'

PolyversCmd.flags = {
    ## Copied from Application
    #
    'show-config': ({
        'Application': {
            'show_config': True,
        },
    }, trc.Application.show_config.help),
    'show-config-json': ({
        'Application': {
            'show_config_json': True,
        },
    }, trc.Application.show_config_json.help),

    ## Consulted by main.init_logging() if in sys.argv.
    #
    ('v', 'verbose'): (
        {'Spec': {'verbose': True}},
        cmdlets.Spec.verbose.help
    ),
    ('f', 'force'): (
        {'Spec': {'force': True}},
        cmdlets.Spec.force.help
    ),
    ('n', 'dry-run'): (
        {'Spec': {'dry_run': True}},
        cmdlets.Spec.dry_run.help
    ),
    ('d', 'debug'): ({
        'Spec': {
            'debug': True,
        }, 'Application': {
            'show_config': True,
            'raise_config_file_errors': True,
        }},
        cmdlets.Spec.debug.help
    ),

    ('c', 'commit'): (
        {},
        PolyversCmd.commit.help
    ),
    ('a', 'amend'): (
        {'Polyvers': {'amend': True}},
        PolyversCmd.amend.help
    ),
    ('t', 'tag'): (
        {'Project': {'tag': True}},
        pvtags.Project.tag.help
    ),
    ('s', 'sign-tags'): (
        {'Project': {'sign_tags': True}},
        pvtags.Project.sign_tags.help
    ),
}

PolyversCmd.aliases = {
    ('m', 'message'): 'Project.message',
    ('u', 'sign-user'): 'Project.sign_user',
}
