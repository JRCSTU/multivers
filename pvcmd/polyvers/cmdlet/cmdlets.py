#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2015-2018 European Commission (JRC);
# Licensed under the EUPL 1.2+ (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl
#
"""
Utils for building elaborate Commands/Sub-commands with traitlets Application.

## Examples:

To run a base command, use this code::

    cd = MainCmd.make_cmd(argv, **app_init_kwds)  ## `sys.argv` used if `argv` is `None`!
    cmd.start()

To run nested commands and print its output, use :func:`baseapp.chain_cmds()` like that::

    cmd = chain_cmds([MainCmd, Sub1Cmd, Sub2Cmd], argv)  ## `argv` without sub-cmds
    sys.exit(baseapp.pump_cmd(cmd.start()) and 0)

Of course you can mix'n match.

## Configuration and Initialization guidelines for *Spec* and *Cmd* classes

0. The configuration of :class:`HasTraits` instance gets stored in its ``config`` attribute.
1. A :class:`HasTraits` instance receives its configuration from 3 sources, in this order:

  a. code specifying class-properties or running on constructors;
  b. configuration files (*json* or ``.py`` files);
  c. command-line arguments.

2. Constructors must allow for properties to be overwritten on construction; any class-defaults
   must function as defaults for any constructor ``**kwds``.

3. Some utility code depends on trait-defaults (i.e. construction of help-messages),
   so for certain properties (e.g. description), it is preferable to set them
   as traits-with-defaults on class-properties.

4. Listen `Good Bait <https://www.youtube.com/watch?v=CE4bl5rk5OQ>`_ after 1:43.

.. [#] http://traitlets.readthedocs.io/
"""

from collections import OrderedDict
from os import PathLike
from typing import (
    Union, Optional, ContextManager,
    Callable, )  # @UnusedImport
import contextlib
import io
import logging
import os
import re

from boltons.setutils import IndexedSet as iset

import os.path as osp

from . import interpctxt
from .._vendor import traitlets as trt
from .._vendor.traitlets import config as trc
from .._vendor.traitlets.traitlets import (
    List as ListTrait, Union as UnionTrait
)  # @UnresolvedImport
from .._vendor.traitlets.traitlets import Bool, Unicode, Instance
from ..utils import fileutil as fu
from .yamlconfloader import YAMLFileConfigLoader


log = logging.getLogger(__name__)


def class2cmd_name(cls):
    name = cls.__name__
    if name.lower().endswith('cmd') and len(name) > 3:
        name = name[:-3]

    return (
        # Turns 'FOOBarCmd' --> 'FOO_Bar_Cmd'
        re.sub('(?<=[a-z0-9])([A-Z]+)', r'_\1', name).  # ('(?!^)([A-Z]+)')
        lower().
        # 'foo_bar_cmd' --> 'foo-bar-cmd'
        replace('_', '-'))


def first_line(doc):
    for l in doc.split('\n'):
        if l.strip():
            return l.strip()


def _set_also_read_only_trait_values(self, **trait_values):
    """Allow to set even `read_only` values."""
    for k, v in trait_values.items():
        self.set_trait(k, v)


trt.HasTraits.set_trait_values = _set_also_read_only_trait_values  # type: ignore


_no_app_help_message = "<Help for '%s' is missing>"


def class_help_description_lines(app_class):
    """
    "Note: Reverse doc/description order bc classes
    do not have dynamic default :meth:`_desc`, below.
    """
    desc = getattr(app_class, '__doc__', None)
    if not desc:
        desc_trait = app_class.class_traits().get('description')
        if desc_trait:
            desc = desc_trait.default_value
    desc = (isinstance(desc, str) and desc or _no_app_help_message % app_class)
    return trc.wrap_paragraphs(desc + '\n')


def cmd_class_short_help(app_class):
    return class_help_description_lines(app_class)[0]


def build_sub_cmds(*subapp_classes):
    """Builds an ordered-dictionary of ``cmd-name --> (cmd-class, help-msg)``. """
    return OrderedDict((class2cmd_name(sa), (sa, cmd_class_short_help(sa)))
                       for sa in subapp_classes)


def cmd_line_chain(cmd):
    """Utility returning the cmd-line(str) that launched a :class:`Cmd`."""
    return ' '.join(c.name for c in reversed(cmd.my_cmd_chain()))


def chain_cmds(app_classes, argv=None, **root_kwds):
    """
    Instantiate a list of ``[cmd, subcmd, ...]``, linking children to parents.

    :param app_classes:
        A list of cmd-classes: ``[root, sub1, sub2, app]``
        Note: you have to "know" the correct nesting-order of the commands ;-)
    :param argv:
        cmdline args are passed to all cmds; make sure they do not contain
        any sub-cmds, or chain will be broken.
        Like :meth:`initialize()`, if undefined, replaced with ``sys.argv[1:]``.
    :return:
        The root(1st) cmd to invoke :meth:`Aplication.start()`

    Apply the :func:`pump_cmd()` or `collect_cmd()` on the return instance.

    - Normally `argv` contain any sub-commands, and it is enough to invoke
      ``initialize(argv)`` on the root cmd.  This function shortcuts
      arg-parsing for subcmds with explict cmd-chaining in code.
    - This functions is the 1st half of :meth:`Cmd.launch_instance()`.
    """
    if not app_classes:
        raise ValueError("No cmds to chained passed in!")

    app_classes = list(app_classes)
    root = app = None
    for app_cl in app_classes:
        if not isinstance(app_cl, type(trc.Application)):
            raise ValueError("Expected an Application-class instance, got %r!" % app_cl)
        if not root:
            ## The 1st cmd is always orphan, and gets returned.
            root = app = app_cl(**root_kwds)
        else:
            app.subapp = app = app_cl(parent=app)
        app.initialize(argv)

    app_classes[0]._instance = app

    return root


class CfgFilesRegistry(contextlib.ContextDecorator):
    """
    Locate and account extensioned files (by default ``.json|.py``).

    - Collects a Locate and (``.json|.py``) files present in the `path_list`, or
    - Invoke this for every "manually" visited config-file, successful or not.
    - Files collected earlier should override next ones.
    """

    def __init__(self, supported_cfg_extensions='.json .py'.split()):
        """
        :param list supported_cfg_extensions:
            file extension (with dot) in the order to search.
        """
        self.supported_cfg_extensions = tuple(supported_cfg_extensions)
        self._visited_tuples = []

    #: A list of 2-tuples ``(folder, fname(s))`` with loaded config-files
    #: in ascending order (last overrides earlier).
    _visited_tuples = None

    @property
    def config_tuples(self):
        """
        The consolidated list of loaded 2-tuples ``(folder, fname(s))``.

        Sorted in descending order (1st overrides later).
        """
        return self._consolidate(self._visited_tuples)

    @staticmethod
    def _consolidate(visited_tuples):
        """
        Reverse and remove multiple, empty records.

        Example::

            >>> CfgFilesRegistry._consolidate([
            ... ('a/b/', None),
            ... ('a/b/', 'F1'),
            ... ('a/b/', 'F2'),
            ... ('a/b/', None),
            ... ('c/c/', None),
            ... ('c/c/', None),
            ... ('d/',   'F1'),
            ... ('d/',   None),
            ... ('c/c/', 'FF')])
            [('a/b/',   ['F1', 'F2']),
             ('c/c/',   []),
             ('d/',     ['F1']),
             ('c/c/',   ['FF'])]
        """
        consolidated = []
        prev = None
        for b, f in visited_tuples:
            if not prev:            # loop start
                prev = (b, [])
            elif prev[0] != b:      # new dir
                consolidated.append(prev)
                prev = (b, [])
            if f:
                prev[1].append(f)
        if prev:
            consolidated.append(prev)

        return consolidated

    def visit_file(self, fpath, loaded):
        """
        Invoke this in ascending order for every visited config-file.

        :param bool loaded:
            Loaded successful?
        """
        base, fname = osp.split(fpath)
        if loaded:
            self.collected_paths.add(fpath)
            pair = (base, fname)
        else:
            pair = (base, None)
        self._visited_tuples.append(pair)

    def collect_fpaths(self, path_list):
        """
        Collects all (``.json|.py``) files present in the `path_list`, (descending order).

        :param path_list:
            A list of paths (absolute, relative, dir or folders).
        :type path_list:
            List[Text]
        :return:
            fully-normalized paths, with ext
        """
        collected_paths = self.collected_paths = iset()
        cfg_exts = self.supported_cfg_extensions

        def try_file_extensions(basepath):
            loaded_any = False
            for ext in cfg_exts:
                f = fu.ensure_file_ext(basepath, ext)
                if f in collected_paths:
                    continue

                loaded = osp.isfile(f)
                self.visit_file(f, loaded=loaded)
                loaded_any |= loaded

            ## Load any files in `conf.d/`, alphabetically-sorted.
            #
            for ext in ('', ) + cfg_exts:
                if basepath.endswith(ext):
                    conf_d = fu.ensure_file_ext(basepath.rstrip(ext), '.d')
                    if os.path.isdir(conf_d):
                        for f in sorted(os.listdir(conf_d)):
                            loaded = f.endswith(cfg_exts)
                            self.visit_file(osp.join(conf_d, f),
                                            loaded=loaded)
                            loaded_any |= loaded

            return loaded_any

        def _derive_config_fpaths(path):  # -> List[Text]:  TODO: enable cmdlet typing comments
            """Return multiple *existent* fpaths for each config-file path (folder/file)."""

            p = fu.convpath(path)
            loaded_any = try_file_extensions(p)
            ## Do not strip ext if has matched WITH ext.
            if not loaded_any:
                try_file_extensions(osp.splitext(p)[0])

        for cf in path_list:
            _derive_config_fpaths(cf)

        return list(collected_paths)

    def head_folder(self):
        """The *last* existing visited folder (if any), even if not containing files."""
        for dirpath, _ in self.config_tuples:
            if osp.exists(dirpath):
                assert osp.isdir(dirpath), ("Expected to be a folder:", dirpath)
                return dirpath


class PathList(ListTrait):
    """Trait that splits unicode strings on `os.pathsep` to form a the list of paths."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args,
                         trait=UnionTrait((Unicode(), Instance(PathLike))),
                         **kwargs)

    def validate(self, obj, value):
        """break all elements also into `os.pathsep` segments"""
        value = super().validate(obj, value)
        value = [os.fspath(cf2)
                 for cf1 in value
                 for cf2 in os.fspath(cf1).split(os.pathsep)]
        return value

    def from_string(self, s):
        if s:
            s = s.split(osp.pathsep)
        return s


class CmdException(Exception):
    pass


class Replaceable:
    """
    A mixin to make :class:`HasTraits` instances clone like namedtupple's ``replace()``.

    :param changes:
        a dict of values keyed be their trait-name.

    Works nicely with *read-only* traits.
    """
    @classmethod
    def new(cls, **trait_values):
        clone = cls()
        clone.set_trait_values(**trait_values)

        return clone

    def replace(self, **changes):
        from copy import copy

        clone = copy(self)
        clone.set_trait_values(**changes)

        return clone

    def _load_config(self, cfg, section_names=None, traits=None):
        """load traits from a Config object"""

        if traits is None:
            traits = self.traits(config=True)
        if section_names is None:
            section_names = self.section_names()

        my_config = self._find_my_config(cfg)

        # hold trait notifications until after all config has been loaded
        with self.hold_trait_notifications():
            from copy import deepcopy
            from .._vendor.traitlets.config.loader import _is_section_key

            for name, config_value in my_config.items():
                if name in traits:
                    if isinstance(config_value, trc.LazyConfigValue):
                        # ConfigValue is a wrapper for using append / update on containers
                        # without having to copy the initial value
                        initial = getattr(self, name)
                        config_value = config_value.get_value(initial)
                    # We have to do a deepcopy here if we don't deepcopy the entire
                    # config object. If we don't, a mutable config_value will be
                    # shared by all instances, effectively making it a class attribute.
                    self.set_trait(name, deepcopy(config_value))
                elif not _is_section_key(name) and not isinstance(config_value, trc.Config):
                    from difflib import get_close_matches
                    if isinstance(self, trc.LoggingConfigurable):
                        warn = self.log.warning
                    else:
                        import warnings

                        warn = lambda msg: warnings.warn(msg, stacklevel=9)
                    matches = get_close_matches(name, traits)
                    msg = u"Config option `{option}` not recognized by `{klass}`.".format(
                        option=name, klass=self.__class__.__name__)

                    if len(matches) == 1:
                        msg += u"  Did you mean `{matches}`?".format(matches=matches[0])
                    elif len(matches) >= 1:
                        msg += "  Did you mean one of: `{matches}`?".format(
                            matches=', '.join(sorted(matches)))
                    warn(msg)


class Printable(metaclass=trt.MetaHasTraits):
    """
    A :class:`HasTraits` mixin making ``str()`` return ``class(trait=value, ...)`` from traits.

    Which traits to print are decided is decided by :class:`TraitSelector`,
    for :attr:`printable_traits` class-property and ``printable=True`` tag.
    """

    def __str__(self):
        from . import traitquery

        tnames_to_print = traitquery.select_traits(self, Printable)
        cls_name = getattr(self, 'name', type(self).__name__)
        trait_values_msg = ', '.join('%s=%s' % (tname, getattr(self, tname))
                                     for tname in tnames_to_print)
        return '%s(%s)' % (cls_name, trait_values_msg)


#: The global :class:`ErrLog` used by :meth:`Forceable.errlogged()`.
_current_errlog = None


def clear_global_errlog():
    global _current_errlog

    log.debug("Clearing global errlog %r.", _current_errlog)
    _current_errlog = None


class Forceable(metaclass=trt.MetaHasTraits):
    """Mixin to facilitate "forcing" actions by ignoring/delaying their errors. """
    force = ListTrait(
        UnionTrait((Bool(), Unicode())),
        config=True,
        help="Force things to perform their duties without complaints.")

    def is_forced(self, token: Union[str, bool] = True):
        """
        Whether some action ided by `token` is allowed to go thorugh in case of errors.

        :param token:
            an optional string/bool to search for in :attr:`force` according
            to the following table::

                               token:
                                    |NONE |
                                    |FALSE|TRUE|"str"|
                 force-element:     |-----|----|-----|
                           [], FALSE|  X  |  X |  X  |
                                TRUE|  X  |  O |  X  |
                                 '*'|  X  |  X |  O  |
                               "str"|  X  |  X |  =  |

            - Rows above, win; columns to the left win.
            - To catch all tokens, use ``--force=true, --force='*'``

        .. Note::
           prefer using it via :class:`ErrLog` contextman.
        """
        assert token is None or isinstance(token, (bool, str)), token
        force = set(self.force)

        if not token or not force or False in force:
            return False

        if token in force:
            return True
        return isinstance(token, str) and '*' in force

    @contextlib.contextmanager
    def errlogged(self,
                  *exceptions,
                  token: Union[bool, str] = None,
                  doing=None,
                  raise_immediately=None,
                  warn_log: Callable = None,
                  info_log: Callable = None
                  ):
        """
        A context-man for nesting :class:`ErrLog` instances.

        - See :class:`ErrLog` for other params.
        - The pre-existing `errlog` is searched in :data:`_current_errlog`
          attribute.
        - The `_current_errlog` on entering context, is restored on exit;
          original is `None`.
        - The returned errlog always has its :attr:`ErrLog.parent` set to
          this enforceable.
        - Example of using this method for multiple actions in a loop::

              with self.errlogged(OSError,
                               doing="loading X-files",
                               token='fread'):
                  for fpath in file_paths:
                      with self.errlogged(doing="reading '%s'" % fpath):
                          fbytes.append(fpath.read_bytes())

              # Any errors collected above, will be raised/WARNed here.

        """
        global _current_errlog

        from . import errlog

        prev_errlog = _current_errlog
        if _current_errlog:

            _current_errlog = _current_errlog(
                *exceptions,
                parent=self,
                token=token, doing=doing,
                raise_immediately=raise_immediately,
                warn_log=warn_log,
                info_log=info_log,
            )
        else:
            ## TODO: decouple `force` from `ErrLog`.
            _current_errlog = errlog.ErrLog(
                self,
                *exceptions,
                token=token, doing=doing,
                raise_immediately=raise_immediately,
                warn_log=warn_log,
                info_log=info_log,
            )

        try:
            yield _current_errlog
        finally:
            _current_errlog = prev_errlog


class CmdletsInterpolation(interpctxt.InterpolationContext):
    """
    Adds `cmdlets_map` into interp-manager for for help & cmd mechanics.

    Client-code may add more dicts in `interpolation_context.maps` list.
    """
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.cmdlets_map = {
            'appname': '<APP>',
            'cmd_chain': '<CMD>',
        }
        self.maps.append(self.cmdlets_map)


#: That's the singleton interp-manager used by all cmdlet configurables.
cmdlets_interpolations = CmdletsInterpolation()


def _travel_parents(self) -> trc.Configurable:
    """
    Utility to travel up parent-chain.

    :return:
        the top parent (or self if no parents)
    """
    while self.parent:
        self = self.parent
    return self


trc.Configurable.root_object = _travel_parents  # type: ignore


def _travel_parents_untill_active_cmd(self, scream=False) -> trc.Application:
    """
    Utility to travel up parent-chain until the active subcmd is met.

    :return:
        the active subcmd, or None if not `scream`
    :raise AssertionError:
        if `scream` and no active subcmd found
    """
    def test_app(app):
        return getattr(app, 'subapp', False) is None

    while self.parent:
        if test_app(self):
            return self
        self = self.parent

    if test_app(self):
        return self

    if scream:
        raise AssertionError('ROOTED!')


#: NOT USED!!
trc.Configurable.active_subcmd = _travel_parents_untill_active_cmd  # type: ignore


class Spec(Forceable, trc.LoggingConfigurable):
    @classmethod
    def class_get_trait_help(cls, trait, inst=None, helptext=None):
        text = super().class_get_trait_help(trait, inst=inst, helptext=helptext)
        obj = inst if inst else cls
        return obj.interpolations.interp(text, _stub_keys=True,
                                         _suppress_errors=True)

    def _log_default(self):
        "Mimic log-hierarchies for Configurable; their loggers are not hierarchical. "
        cls = type(self)
        return logging.getLogger('.'.join((cls.__module__, cls.__name__)))

    verbose = Bool(
        allow_none=True,
        config=True,
        help="Repeated use increase logging-level from WARNING-->INFO-->DEBUG.")

    debug = Bool(
        allow_none=True,
        config=True,
        help="Change certain actions, to discover possible problems.")

    dry_run = Bool(
        allow_none=True,
        config=True,
        help="Do not write files - just pretend.")

    # TODO: refact to hide `Spec.interpolations` attribute.
    interpolations = cmdlets_interpolations

    def ikeys(self, *maps, **kwds) -> ContextManager[CmdletsInterpolation]:
        """
        Temporarily place self before the given maps and kwds in interpolation-cntxt.

        - Self has the least priority, kwds the most.
        - For params, see :meth:`interp.InterpolationContext.interp()`.

        .. NOTE::
           Must use ``str.format_map()`` when `_stub_keys` is true;
           otherwise, ``format()`` will clone all existing keys in
           a static map.
        """
        return self.interpolations.ikeys(self, *maps, **kwds)

    def interp(self, text: Optional[str], *maps, **kwds) -> Optional[str]:
        """
        Interpolate text with self attributes before maps and kwds given.

        :param text:
            the text to interplate; None/empty returned as is

        - For params, see :meth:`interp.InterpolationContext.interp()`.
        - Self has the least priority, kwds the most.
        """
        if not text:
            return text
        with self.ikeys(*maps, **kwds) as cntx:
            new_text = text.format_map(cntx)
        return new_text


class Cmd(trc.Application, Spec):
    "Common machinery for all (sub)commands."

    @classmethod
    def make_cmd(app, argv=None, **kwargs):
        """
        Instanciate, initialize and return application.

        :param argv:
            Like :meth:`initialize()`, if undefined, replaced with ``sys.argv[1:]``.

        - Tip: Apply :func:`pump_cmd()` on return values to process
          generators of :meth:`run()`.
        - This functions is the 1st half of :meth:`launch_instance()` which
          invokes and discards :meth:`start()` results.
        """
        ## Overriden just to return `start()` AND fix ipython/traitlets#474
        #  when cmds inherit same class.
        app.clear_instance()
        cmd = app.instance(**kwargs)
        cmd.initialize(argv)

        return cmd

    @trt.default('name')
    def _name(self):
        """Without it, need to set `name` attr on every class."""
        name = class2cmd_name(type(self))
        return name

    @trt.default('description')
    def _desc(self):
        """Without it, need to set `description` attr on every class."""
        cls = type(self)
        return cls.__doc__ or ''

    def _log_default(self):
        "Mimic log-hierarchies for Configurable; their loggers are not hierarchical. "
        cls = type(self)
        return logging.getLogger('.'.join((cls.__module__, cls.__name__)))

    ##########
    ## HELP ##
    ##########

    option_description = Unicode("""
        Options are convenience aliases to configurable class-params,
        as listed in the "Equivalent to" description-line of the aliases.
        To see all configurable class-params for some <cmd>, use::
            <cmd> --help-all
        or view help for specific parameter using::
            {appname} desc <class>.<param>
    """.strip())

    def emit_description(self):
        ## Overridden for interpolating app-name.
        txt = self.description or self.__doc__ or _no_app_help_message % type(self)
        txt = self.interp(txt, _stub_keys=True,
                          _suppress_errors=True)
        for p in trc.wrap_paragraphs('%s: %s' % (cmd_line_chain(self), txt)):
            yield p
            yield ''

    def emit_options_help(self):
        """Yield the lines for the options part of the help."""
        if not self.flags and not self.aliases:
            return
        header = 'Options'
        yield header
        yield '=' * len(header)
        opt_desc = self.interp(self.option_description, _stub_keys=True,
                               _suppress_errors=True)
        for p in trc.wrap_paragraphs(opt_desc):
            yield p
            yield ''

        for l in self.emit_flag_help():
            yield l
        for l in self.emit_alias_help():
            yield l
        yield ''

    def emit_examples(self):
        ## Overridden for interpolating app-name.
        if self.examples:
            txt = self.interp(self.examples, _stub_keys=True,
                              _suppress_errors=True).strip()
            yield "Examples"
            yield "--------"
            yield ''
            yield trc.indent(trc.dedent(txt))
            yield ''

    def emit_help_epilogue(self, classes=None):
        """Yield the very bottom lines of the help message.

        If classes=False (the default), print `--help-all` msg.
        """
        if not classes:
            epilogue = trc.dedent("""
            --------
            - For available option, configuration-params & examples, use:
                  {cmd_chain} help (OR --help-all)
            - For help on specific classes/params, use:
                  {appname} config desc <class-or-param-1>...
            - To inspect configuration values:
                  {appname} config show <class-or-param-1>...
            """)
            yield self.interp(epilogue, _stub_keys=True,
                              _suppress_errors=True)

    ############
    ## CONFIG ##
    ############

    @trt.observe('parent')
    def _inherit_parent_cmd(self, change):
        if self.parent:
            parent = self.parent

            if parent.flags:
                flags = self.flags
                for k, v in parent.flags.items():
                    flags.setdefault(k, v)

            if parent.aliases:
                aliases = self.aliases
                for k, v in parent.aliases.items():
                    aliases.setdefault(k, v)

            ## Need also classes bc flags/aliases may depend on them
            #
            if parent.classes:
                classes = set(self.classes)
                classes.update(parent.classes)
                self.classes = list(classes)

    config_paths = PathList(
        help="""
        Absolute/relative folder/file path(s) to read "static" config-parameters from.

        - Sources for this parameter can either be CLI or ENV-VAR; since the loading
          of config-files depend on this parameter, file-configs are ignored.
        - Multiple values may be given and each one may be separated by '%(sep)s'.
          Priority is descending, i.e. config-params from the 1st one overrides the rest.
        - For paths resolving to existing folders, the filenames `<basename>(.py|.json)`
          are appended and searched (in this order); otherwise, any file-extension
          is ignored, and the mentioned extensions are combined and searched.

        Tips:
          - Use `config infos` to view the actual paths/files loaded.
          - Use `config write` to produce a skeleton of the config-file.

        Examples:
          To read and apply in descending order: [~/my_conf, /tmp/conf.py, ~/.{appname}.json]
          you may issue:
              <cmd> --config-paths=~/my_conf%(sep)s/tmp/conf.py  --Cmd.config_paths=~/.{appname}.jso
        """ % {'sep': osp.pathsep}
        ## TODO: Simplify path-loading when /ipython/traitlets#242 merged??
        #  NOTE: Patch default-value on `Cmd` so all subcmds load same configs.
    ).tag(config=True)

    _cfgfiles_registry: CfgFilesRegistry = None

    @property
    def loaded_config_files(self):
        return self._cfgfiles_registry and self._cfgfiles_registry.config_tuples or []

    config_basename = Unicode(
        help=""""
        The config-file's basename (no path or extension) to search when not explicitly specified.

        By default, it's the root app's name, prefixed with a dot('.').
        """)

    @trt.default('config_basename')
    def _config_basename(self):
        return '.' + self.root_object().name

    def _collect_static_fpaths(self):
        """Return fully-normalized paths, with ext."""
        config_paths = self.config_paths
        self._cfgfiles_registry = CfgFilesRegistry('.json .yaml .py'.split())
        fpaths = self._cfgfiles_registry.collect_fpaths(config_paths)

        return fpaths

    def _read_supported_configs(self, cfpath):
        """
        :param str cfpath:
            The absolute config-file path with either ``.py`` or ``.json`` ext.
        """
        log = self.log
        loaders = {
            '.py': trc.PyFileConfigLoader,
            '.json': trc.JSONFileConfigLoader,
            '.yaml': YAMLFileConfigLoader,
        }
        ext = osp.splitext(cfpath)[1]
        loader = loaders.get(str.lower(ext))
        assert loader, cfpath  # Must exist.

        config = None
        try:
            config = loader(cfpath, path=None, log=log).load_config()
        except trc.ConfigFileNotFound:
            ## Config-file deleted between collecting its name and reading it.
            pass
        except Exception as ex:
            if self.raise_config_file_errors:
                raise
            log.error("Failed loading config-file '%s' due to: %s",
                      cfpath, ex, exc_info=True)
        else:
            log.debug("Loaded config-file: %s", cfpath)

        return config

    def read_config_files(self):  # -> trc.Config
        """
        Load :attr:`config_paths` and maintain :attr:`config_registry`.

        :param config_paths:
            full normalized paths (descending order, 1st overrides the rest)
        :return:
            the static_config loaded

        - Configuration files are read and merged from ``.json`` and/or ``.py`` files
          in :attribute:`config_paths`.
        """
        ## Adapted from :meth:`load_config_file()` & :meth:`_load_config_files()`.
        config_paths = self._collect_static_fpaths()

        new_config = trc.Config()
        ## Registry to detect collisions.
        loaded = {}  # type: Dict[Text, Config]

        for cfpath in config_paths[::-1]:
            config = self._read_supported_configs(cfpath)
            if config:
                for filename, earlier_config in loaded.items():
                    collisions = earlier_config.collisions(config)
                    if collisions:
                        import json
                        self.log.warning(
                            "Collisions detected in %s and %s config files."
                            " %s has higher priority: %s",
                            filename, cfpath, cfpath,
                            json.dumps(collisions, indent=2)
                        )
                loaded[cfpath] = config

                new_config.merge(config)

        return new_config

    def write_default_config(self, config_file=None, force=False):
        if config_file:
            config_file = fu.convpath(config_file)
            if osp.isdir(config_file):
                config_file = osp.join(config_file, self.config_basename)
        elif self.config_paths:
            config_file = self.config_paths[0]
        else:
            raise AssertionError("No config-file given to write to!")

        config_file = fu.ensure_file_ext(config_file, '.py')

        is_overwrite = osp.isfile(config_file)
        if is_overwrite:
            if not force:
                raise CmdException("Config-file '%s' already exists!"
                                   "\n  Specify `--force` to overwrite." % config_file)
            else:
                import shutil
                from datetime import datetime

                now = datetime.now().strftime('%Y%m%d-%H%M%S%Z')
                backup_name = '%s-%s.py' % (osp.splitext(config_file)[0], now)
                shutil.move(config_file, backup_name)

                op_msg = ", old file renamed --> '%s'" % backup_name
        else:
            op_msg = ""

        self.log.info("Writting config-file '%s'%s...", config_file, op_msg)
        fu.ensure_dir_exists(os.path.dirname(config_file), 0o700)
        config_text = self.generate_config_file()
        with io.open(config_file, mode='wt') as fp:
            fp.write(config_text)

    all_app_configurables = ListTrait(
        help="""
        A sequence of all app configurables to feed into `config` sub-command.

        Defined either on :class:`Cmd` superclass or on *root-cmd*.
        """
    )

    #############
    ## SUBAPPS ##
    #############
    ## Overriden for existing sub-apps to die and new ones to receive parents
    #  even when hierarchy changes (e.g. in TCs).
    #  See https://github.com/ipython/traitlets/commit/e857996#commitcomment-27681994

    @trc.catch_config_error  # Needed, bc does not invoke super().
    def initialize_subcommand(self, subc, argv=None):
        subapp, _ = self.subcommands.get(subc)

        if isinstance(subapp, trc.six.string_types):
            subapp = trc.import_item(subapp)

        ## Cannot issubclass() on a non-type (SOhttp://stackoverflow.com/questions/8692430)
        if isinstance(subapp, type) and issubclass(subapp, trc.Application):
            # Clear existing instances before...
            #type(self).clear_instance()
            subapp.clear_instance()
            # instantiating subapp...
            self.subapp = subapp.instance(parent=self)
        elif callable(subapp):
            # or ask factory to create it...
            self.subapp = subapp(self)
        else:
            raise AssertionError("Invalid mappings for subcommand '%s'!" % subc)

        # ... and finally initialize subapp.
        self.subapp.initialize(argv)

    @classmethod
    def clear_instance(cls):
        if not cls.initialized():
            return
        cls._instance = None

    @classmethod
    def instance(cls, *args, **kwargs):
        # Create and save the instance
        if cls._instance is None:
            inst = cls(*args, **kwargs)
            obj = cls._instance = inst

        elif isinstance(cls._instance, cls):
            obj = cls._instance
        else:
            raise trc.MultipleInstanceError(
                "An incompatible sibling of '%s' is already instanciated"
                " as singleton: %s" % (cls.__name__, type(cls._instance).__name__)
            )

        return obj

    #############
    ## STARTUP ##
    #############

    def my_cmd_chain(self):
        """Return the chain of cmd-classes starting from my self or subapp."""
        cmd_chain = []
        pcl = self.subapp if self.subapp else self
        while pcl:
            cmd_chain.append(pcl)
            pcl = pcl.parent

        return cmd_chain

    def _is_dispatching(self):
        """True if dispatching to another command."""
        return isinstance(self.subapp, trc.Application)  # subapp == trait | subcmd | None

    def update_interp_context(self, argv=None):
        cmdlets_map = self.interpolations.cmdlets_map
        cmdlets_map['cmd_chain'] = cmd_line_chain(self)
        cmdlets_map['appname'] = self.root_object().name

    #@trc.catch_config_error NOT needed, invoking super()!
    def initialize(self, argv=None):
        """
        Invoked after __init__() by `make_cmd()` to apply configs and build subapps.

        :param argv:
            If undefined, they are replaced with ``sys.argv[1:]``!

        It parses cl-args before file-configs, to detect sub-commands
        and update any :attr:`config_paths`, then it reads all file-configs, and
        then re-apply cmd-line configs as overrides (trick copied from `jupyter-core`).
        """
        self.update_interp_context()
        super().initialize(argv)
        if self._is_dispatching():
            ## Only the final child reads file-configs.
            #  Also avoid contaminations with user if generating-config.
            return

        config = self.read_config_files()
        config.merge(self.cli_config)

        ## Ensure cmd-chain configured, or else
        #  root-app would have been configed only from cmd-line args.
        #
        while self:
            self.update_config(config)
            self = self.parent

    def start(self):
        """Dispatches into sub-cmds (if any), and then delegates to :meth:`run().

        If overriden, better invoke :func:`super()`, but even better
        to override :meth:``run()`.
        """
        if self.subapp is None:
            res = self.run(*self.extra_args)

            return res

        return self.subapp.start()

    def run(self, *args):
        """Leaf sub-commands must inherit this instead of :meth:`start()` without invoking :func:`super()`.

        :param args:
            Invoked by :meth:`start()` with :attr:`extra_args`.

        By default, screams about using sub-cmds, or about doing nothing!
        """
        import ipython_genutils.text as tw

        assert self.subcommands, "Override run() method in cmd subclasses."

        if args:
            subcmd_msg = "unknown sub-command `%s`!" % args[0]
        else:
            subcmd_msg = "sub-command is missing!"
        subcmds = '\n'.join('  %10s: %s' % (k, desc) for k, (_, desc)
                            in self.subcommands.items())
        msg = tw.dedent(
            """
            %(cmd_chain)s: %(subcmd_msg)s

              Try one of:
            %(subcmds)s
            %(epilogue)s""") % {
                'subcmd_msg': subcmd_msg,
                'cmd_chain': cmd_line_chain(self),
                'subcmds': subcmds,
                'epilogue': '\n'.join(self.emit_help_epilogue()),
        }
        raise CmdException(msg)


##################
## YAML CONFIGS ##
## patch traits ##
##################

def class_config_yaml(cls, outer_cfg, classes=None):
    """Get the config section for this Configurable.

    Parameters
    ----------
    classes: list, optional
        The list of other classes in the config file.
        Used to reduce redundant information.
    """
    from ..utils import yamlutil
    from ruamel.yaml.comments import CommentedMap  # @UnresolvedImport
    from ipython_genutils.text import wrap_paragraphs
    import textwrap as tw

    def comment(s):
        """return a commented, wrapped block."""
        return '\n\n'.join(wrap_paragraphs(s, 78)) + '\n'

    # section header
    breaker = '#' * 76
    parent_classes = ', '.join(
        p.__name__ for p in cls.__bases__
        if issubclass(p, trc.Configurable)
    )

    s = "%s(%s) configuration" % (cls.__name__, parent_classes)
    head_lines = [breaker, s, breaker]
    # get the description trait
    desc = cls.class_traits().get('description')
    if desc:
        desc = desc.default_value
    if not desc:
        # no description from trait, use __doc__
        desc = getattr(cls, '__doc__', '')
    if desc:
        head_lines.append(comment(desc))
        head_lines.append('')
    outer_cfg[cls.__name__] = cfg = CommentedMap()
    cfg.yaml_set_start_comment('\n'.join(head_lines))

    for name, trait in sorted(cls.class_traits(config=True).items()):
        cfg[name] = trait.default()
        trait_lines = []
        default_value = trait.default()
        default_repr = yamlutil.ydumps(default_value)
        if default_repr and default_repr.count('\n') > 1 and default_repr[0] != '\n':
            default_repr = tw.indent('\n' + default_repr, ' ' * 9)

        if classes:
            defining_class = cls._defining_class(trait, classes)
        else:
            defining_class = cls
        if defining_class is cls:
            # cls owns the trait, show full help
            if trait.help:
                trait_lines.append('')
                trait_lines.append(comment(trait.help).strip())
            if 'Enum' in type(trait).__name__:
                # include Enum choices
                trait_lines.append('Choices: %s' % trait.info())
            trait_lines.append('Default: %s' % default_repr)
        else:
            # Trait appears multiple times and isn't defined here.
            # Truncate help to first line + "See also Original.trait"
            if trait.help:
                trait_lines.append(comment(trait.help.split('\n', 1)[0]))
            trait_lines.append('See also: %s.%s' % (defining_class.__name__, name))

        cfg.yaml_set_comment_before_after_key(name, before='\n'.join(trait_lines))


trc.Configurable.class_config_yaml = classmethod(class_config_yaml)  # type: ignore


def order_class_hierarchy(classes, mro_func=lambda cls: cls.mro()):
    visited_index = {}  # invered-hierarchy index: {sub: super}
    ordered = []

    def visit_class(cls):
        nonlocal ordered

        assert cls not in visited_index, (cls, visited_index, classes)

        mro = mro_func(cls)
        if set(mro) & visited_index.keys():
            ## Visiting a super of existing classes.
            #
            ## Replace all it's subclasses in`ordered` with it.
            #
            ordered = [c for c in ordered
                       if c not in mro]

        ordered.extend(mro)

        ## Update all subclasses in hierarchy-index.
        #
        for sub in mro:
            visited_index[sub] = cls

    for cls in classes:
        if cls not in visited_index:
            visit_class(cls)

    return ordered


def generate_class_hierarchy_text(classes):
    def class_line(cls):
        bases = [base for base in cls.__bases__
                 if base in classes]
        max_class_name_len = max(len(cls.__name__) for cls in classes)
        if bases:
            fmt = '  %%-%is --> %%s' % max_class_name_len
            return fmt % (cls.__name__,
                          ', '.join(b.__name__ for b in bases))
        else:
            fmt = '  %%-%is' % max_class_name_len
            return fmt % cls.__name__

    return '\n'.join(class_line(cls) for cls in classes)


def generate_config_file_yaml(self, classes=None):
    """generate default config file from Configurables"""
    from ruamel.yaml.comments import CommentedMap  # @UnresolvedImport
    import ipython_genutils.text as tw

    classes = self.classes if classes is None else classes

    def mro_for_specs(cls):
        return [sub for sub in cls.mro() if issubclass(sub, Spec)]

    ordered_classes = order_class_hierarchy(
        classes,
        mro_func=mro_for_specs)

    class_hiearchy = generate_class_hierarchy_text(ordered_classes)
    start_comment = tw.dedent("""
        ####################################
        Configuration file for `%s`.

        Class-hierarchy:
        %s
        ####################################

    """) % (self.root_object().name, class_hiearchy)

    cfg = CommentedMap()
    cfg.yaml_set_start_comment(start_comment)

    config_classes = list(self._classes_with_config_traits(classes))
    for cls in config_classes:
        cls.class_config_yaml(cfg)

    return cfg


trc.Application.generate_config_file_yaml = generate_config_file_yaml  # type: ignore
