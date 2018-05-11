#! python
# -*- coding: UTF-8 -*-
#
# Copyright 2015-2017 European Commission (JRC);
# Licensed under the EUPL (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl

from os import pathsep as PS
from polyvers._vendor.traitlets import traitlets as trt, config as trc
from polyvers._vendor.traitlets.traitlets import Int
from polyvers.cmdlet import cmdlets, traitquery
from polyvers.utils import logconfutils as lcu
from polyvers.utils.yamlutil import ydumps
from tests.conftest import touchpaths
import logging
import os

from ruamel.yaml.comments import CommentedMap
import pytest

from py.path import local as P  # @UnresolvedImport
import os.path as osp
import textwrap as tw


lcu.init_logging(level=logging.DEBUG, logconf=[])

log = logging.getLogger(__name__)

mydir = osp.dirname(__file__)


def test_Replaceable():
    class C(cmdlets.Replaceable, trt.HasTraits):
        a = Int()

    c = C(a=1)
    assert c.a == 1

    cc = c.replace(a=2)
    assert cc.a == 2
    assert c.a == 1


def test_Replaceable_Configurable():
    c = trc.Config()
    c.C.a = 1
    c.C.b = 1

    class C(trc.Configurable, cmdlets.Replaceable):
        a = Int(config=1)
        b = Int(config=1)

    c1 = C(config=c)
    assert c1.a == c1.b == 1

    c2 = c1.replace(b=2)
    assert c2.a == 1
    assert c2.b == 2


def test_Printable_smoketest():
    class C(trt.HasTraits, cmdlets.Printable):
        c = Int()

    c = C(c=1)
    got = traitquery.select_traits(c, cmdlets.Printable,
                                   printable=True)
    assert isinstance(got, dict)
    assert list(got) == ['c']
    assert str(c) == 'C(c=1)'

    class D(C):
        d = Int()

    d = D()
    got = traitquery.select_traits(d, cmdlets.Printable,
                                   printable=True)
    assert isinstance(got, dict)
    assert set(got) == {'c', 'd'}
    assert str(D()) == 'D(c=0, d=0)'  # mro trait definition

    D.d.metadata['printable'] = True
    d = D()
    got = traitquery.select_traits(d, cmdlets.Printable,
                                   printable=True)
    assert isinstance(got, dict)
    assert set(got) == {'d'}

    ## Check no mixin.
    #
    got = traitquery.select_traits(d, printable=True)
    assert set(got) == {'d'}
    assert isinstance(got, dict)
    del D.d.metadata['printable']
    assert not traitquery.select_traits(d, printable=True)


def check_select_traits(classprop, C, D, c_ptraits, d_ptraits, c_exp, d_exp,
                        append_tags=False):
    def check(cls, exp):
        c = cls()
        if isinstance(exp, Exception):
            with pytest.raises(type(exp), match=str(exp)):
                traitquery.select_traits(c, cmdlets.Printable,
                                         append_tags=append_tags,
                                         printable=True)
        else:
            got = traitquery.select_traits(c, cmdlets.Printable,
                                           append_tags=append_tags,
                                           printable=True)
            assert isinstance(got, dict)
            assert set(got) == set(exp)

    if c_ptraits is not None:
        p = c_ptraits
        if len(p) > 1:
            p = list(p)
        setattr(C, classprop, p)

    if d_ptraits is not None:
        p = d_ptraits
        if len(p) > 1:
            p = list(p)
        setattr(D, classprop, p)

    if c_exp is not None:
        check(C, c_exp)

    if d_exp is not None:
        check(D, d_exp)


@pytest.mark.parametrize('c_ptraits, d_ptraits, c_exp, d_exp', [
    (list('cd'), None,
     ValueError("C.printable_traits` contains unknown trait-names"), 'cd'),
    (None, 'x', 'c', ValueError("D.printable_traits` contains unknown trait-names")),

    (None, None, 'c', 'cd'),
    ('*', None, 'c', 'cd'),
    (None, '*', 'c', 'cd'),

    ((), None, (), ()),
    (None, (), 'c', ()),
    ('', (), (), ()),
    ((), '*', (), 'cd'),
    ('*', (), 'c', ()),

    ('-', None, 'c', 'c'),
    (None, '-', 'c', 'd'),
    (['-'], '-', 'c', 'd'),
    ('*', ['-'], 'c', 'd'),
    ('-', '*', 'c', 'cd'),

    ('c', 'd', 'c', 'd'),
    ('c', list('-d'), 'c', 'd'),

    ('c', '', 'c', ()),
    ('', 'd', (), 'd'),
])
def test_TraitSelector_clsprop(c_ptraits, d_ptraits, c_exp, d_exp):
    class C(trt.HasTraits, cmdlets.Printable):
        c = Int()

    class D(C):
        d = Int()

    check_select_traits('printable_traits', C, D, c_ptraits, d_ptraits, c_exp, d_exp)


@pytest.mark.parametrize('c_ptraits, d_ptraits, c_exp, d_exp', [
    (list('cd'), None,
     ValueError("C.printable_traits` contains unknown trait-names"), 'cd'),
    (None, 'x', 'a', ValueError("D.printable_traits` contains unknown trait-names")),

    (None, None, 'a', 'ab'),
    ('*', None, 'ac', 'abcd'),
    (None, '*', 'a', 'abcd'),

    ((), None, (), ()),
    (None, (), 'a', ()),
    ('', (), (), ()),
    ((), '*', (), 'abcd'),
    ('*', (), 'ac', ()),
    ('*', '', 'ac', ()),

    ('-', None, 'ac', 'ac'),
    (None, '-', 'a', 'bd'),
    (['-'], '-', 'ac', 'bd'),
    ('*', ['-'], 'ac', 'bd'),
    ('-', '*', 'ac', 'abcd'),

    ('c', 'd', 'c', 'd'),
    ('c', list('-d'), 'c', 'bd'),

    ## refer to a trait in mro above mixin.
    ('wc', 'yb', 'cw', 'by'),
])
def test_TraitSelector_clsprop_tags(c_ptraits, d_ptraits, c_exp, d_exp):
    class B(trt.HasTraits):
        w = Int().tag(printable=True)
        y = Int()
        pass

    class C(B, cmdlets.Printable):
        a = Int().tag(printable=True)
        c = Int()

    class D(C):
        b = Int().tag(printable=True)
        d = Int()

    check_select_traits('printable_traits', C, D, c_ptraits, d_ptraits, c_exp, d_exp)


@pytest.mark.parametrize('c_ptraits, d_ptraits, c_exp, d_exp', [
    ((), None, (), ()),
    (None, (), 'a', ()),
    ('', (), (), ()),

    ('-', None, 'ac', 'abc'),

    ('c', 'd', 'ac', 'abd'),
    ('', list('-d'), (), 'abd'),
])
def test_TraitSelector_clsprop_tags_appended(c_ptraits, d_ptraits, c_exp, d_exp):
    class C(trt.HasTraits, cmdlets.Printable):
        a = Int().tag(printable=True)
        c = Int()

    class D(C):
        b = Int().tag(printable=True)
        d = Int()

    check_select_traits('printable_traits', C, D, c_ptraits, d_ptraits, c_exp, d_exp,
                        append_tags=True)


@pytest.mark.parametrize('force, token, exp', [
    ([], 'abc', False),
    ([], None, False),
    (False, None, False),
    (False, False, False),
    (False, 'abc', False),
    ([], 'abc', False),
    ('abc', None, False),
    (' abc ', 'abc', False),    # no stripping
    ('abc def', ' abc ', False),  # no splitting

    (True, None, False),
    (True, False, False),
    ('*', None, False),
    ('*', False, False),
    (True, 'abc', False),

    ('abc', 'abc', True),
    ('*', 'abc', True),

    ## False force short-circuits to false.
    #
    ([True, 'abc', False], None, False),
    ([False, 'abc'], None, False),
    (['*', 'abc'], True, False),
    ([True, 'abc', False], 'abc', False),
    ([True, '*', 'abc', False], 'abc', False),
    ([True, False], True, False),
    ([False, True], True, False),

    ([True, 'abc', True, ], 'abc', True),
    ([True, 'FOO', 'abc'], 'abc', True),
    ([True, 'FOO', '*'], 'abc', True),
    ([True, 'BAD'], True, True),
    ([True, '*'], True, True),
    ('ad bb tt gg'.split(), 'ad', True),
    ('ad bb tt gg'.split(), 'tt', True),
    ('ad bb tt gg'.split(), 'gg', True),

    ('aa bb', 'aa bb', True),
])
def test_Forceable_is_forced(force, token, exp):
    if not isinstance(force, list):
        force = [force]
    sp = cmdlets.Spec(force=force)
    assert sp.is_forced(token) is exp


def test_errlog_thread_context():
    class F(cmdlets.Forceable, trt.HasTraits):
        pass

    frc1 = F()
    frc2 = F()

    with frc1.errlogged() as erl1:
        assert erl1.parent == frc1
        assert cmdlets._current_errlog is erl1
        with frc2.errlogged() as erl2:
            assert cmdlets._current_errlog is erl2
            assert erl2.parent == frc2
            assert erl1._root_node is erl2._root_node
        assert cmdlets._current_errlog is erl1
    assert cmdlets._current_errlog is None


def test_CfgFilesRegistry_consolidate_posix_1():
    visited = [
        ('/d/foo/bar/.appname', None),
        ('/d/foo/bar/.appname', 'appname_config.py'),
        ('/d/foo/bar/.appname', 'appname_config.json'),
        ('/d/foo\\Bar/dooba/doo', None),
        ('/d/foo\\Bar/dooba/doo', None),
        ('/d/foo\\Bar/dooba/doo', None),
        ('/d/foo\\Bar/dooba/doo', None),
    ]
    c = cmdlets.CfgFilesRegistry()
    cons = c._consolidate(visited)

    exp = [
        ('/d/foo/bar/.appname', ['appname_config.py', 'appname_config.json']),
        ('/d/foo\\Bar/dooba/doo', []),
    ]
    #print('FF\n', cons)
    assert cons == exp


def test_CfgFilesRegistry_consolidate_posix_2():
    visited = [
        ('/c/Big/BEAR/.appname', 'appname_persist.json'),
        ('/c/Big/BEAR/.appname', 'appname_config.py'),
        ('/c/Big/BEAR/.appname', None),
        ('/d/foo\\Bar/dooba/doo', None),
        ('/d/foo\\Bar/dooba/doo', None),
        ('/d/foo\\Bar/dooba/doo', None),
        ('/d/foo\\Bar/dooba/doo', None),
    ]
    c = cmdlets.CfgFilesRegistry()
    cons = c._consolidate(visited)

    exp = [
        ('/c/Big/BEAR/.appname', ['appname_persist.json', 'appname_config.py']),
        ('/d/foo\\Bar/dooba/doo', []),
    ]
    #print('FF\n', cons)
    assert cons == exp


def test_CfgFilesRegistry_consolidate_win_1():
    visited = [
        ('D:\\foo\\bar\\.appname', None),
        ('D:\\foo\\bar\\.appname', 'appname_config.py'),
        ('D:\\foo\\bar\\.appname', 'appname_config.json'),
        ('d:\\foo\\Bar\\dooba\\doo', None),
        ('d:\\foo\\Bar\\dooba\\doo', None),
        ('d:\\foo\\Bar\\dooba\\doo', None),
        ('d:\\foo\\Bar\\dooba\\doo', None),
    ]
    c = cmdlets.CfgFilesRegistry()
    cons = c._consolidate(visited)

    exp = [
        ('D:\\foo\\bar\\.appname', ['appname_config.py', 'appname_config.json']),
        ('d:\\foo\\Bar\\dooba\\doo', []),
    ]
    #print('FF\n', cons)
    assert cons == exp


def test_CfgFilesRegistry_consolidate_win_2():
    visited = [
        ('C:\\Big\\BEAR\\.appname', 'appname_persist.json'),
        ('C:\\Big\\BEAR\\.appname', 'appname_config.py'),
        ('C:\\Big\\BEAR\\.appname', None),
        ('D:\\foo\\Bar\\dooba\\doo', None),
        ('D:\\foo\\Bar\\dooba\\doo', None),
        ('D:\\foo\\Bar\\dooba\\doo', None),
        ('D:\\foo\\Bar\\dooba\\doo', None),
    ]
    c = cmdlets.CfgFilesRegistry()
    cons = c._consolidate(visited)

    exp = [
        ('C:\\Big\\BEAR\\.appname', ['appname_persist.json', 'appname_config.py']),
        ('D:\\foo\\Bar\\dooba\\doo', []),
    ]
    #print('FF\n', cons)
    assert cons == exp


def test_CfgFilesRegistry(tmpdir):
    tdir = tmpdir.mkdir('cfgregistry')
    tdir.chdir()
    paths = """
    ## loaded
    #
    conf.py
    conf.json
    conf.d/a.json
    conf.d/a.py

    ## ignored
    #
    conf
    conf.bad
    conf.d/conf.bad
    conf.d/bad
    conf.py.d/a.json
    conf.json.d/a.json
    """
    touchpaths(tdir, paths)

    cfr = cmdlets.CfgFilesRegistry()
    fpaths = cfr.collect_fpaths(['conf'])
    fpaths = [P(p).relto(tdir).replace('\\', '/') for p in fpaths]
    assert fpaths == 'conf.json conf.py conf.d/a.json conf.d/a.py'.split()

    cfr = cmdlets.CfgFilesRegistry()
    fpaths = cfr.collect_fpaths(['conf.py'])
    fpaths = [P(p).relto(tdir).replace('\\', '/') for p in fpaths]
    assert fpaths == 'conf.py conf.py.d/a.json conf.d/a.json conf.d/a.py'.split()


def test_no_default_config_paths(tmpdir):
    cwd = tmpdir.mkdir('cwd')
    cwd.chdir()

    home = tmpdir.mkdir('home')
    os.environ['HOME'] = str(home)

    c = cmdlets.Cmd()
    c.initialize([])
    print(c._cfgfiles_registry.config_tuples)
    assert len(c.loaded_config_files) == 0


def test_default_loaded_paths(tmpdir):
    tdir = tmpdir.mkdir('cwd')
    c = cmdlets.Cmd(config_paths=[tdir])
    c.initialize([])
    print(c._cfgfiles_registry.config_tuples)
    assert len(c.loaded_config_files) == 1


test_paths0 = [
    ([], []),
    (['cc', 'cc.json'], ['cc', 'cc.json']),
    (['c.json%sc.py' % PS], ['c.json', 'c.py']),
    (['c', 'c.json%sc.py' % PS, 'jjj'], ['c', 'c.json', 'c.py', 'jjj']),
]


@pytest.mark.parametrize('inp, exp', test_paths0)
def test_PathList_trait(inp, exp):
    from pathlib import Path

    class C(trt.HasTraits):
        p = cmdlets.PathList()

    c = C()
    c.p = inp
    assert c.p == exp

    c = C()
    c.p = [Path(i) for i in inp]
    assert c.p == exp


test_paths1 = [
    (None, None, []),
    (['cc', 'cc.json'], None, []),


    ## Because of ext-stripping.
    (['b.py', 'a.json'], None, ['b.json', 'a.py']),
    (['c.json'], None, ['c.json']),

    ([''], None, []),
    (None, 'a', []),
    (None, 'a%s' % PS, []),

    (['a'], None, ['a.py']),
    (['b'], None, ['b.json']),
    (['c'], None, ['c.json', 'c.py']),

    (['c.json', 'c.py'], None, ['c.json', 'c.py']),
    (['c.json%sc.py' % PS], None, ['c.json', 'c.py']),

    (['c', 'c.json%sc.py' % PS], None, ['c.json', 'c.py']),
    (['c%sc.json' % PS, 'c.py'], None, ['c.json', 'c.py']),

    (['a', 'b'], None, ['a.py', 'b.json']),
    (['b', 'a'], None, ['b.json', 'a.py']),
    (['c'], None, ['c.json', 'c.py']),
    (['a', 'c'], None, ['a.py', 'c.json', 'c.py']),
    (['a', 'c'], None, ['a.py', 'c.json', 'c.py']),
    (['a%sc' % PS], None, ['a.py', 'c.json', 'c.py']),
    (['a%sb' % PS, 'c'], None, ['a.py', 'b.json', 'c.json', 'c.py']),

    ('b', 'a', ['b.json']),
]


@pytest.mark.parametrize('param, var, exp', test_paths1)
def test_collect_static_fpaths(param, var, exp, tmpdir):
    tdir = tmpdir.mkdir('collect_paths')

    touchpaths(tdir, """
        a.py
        b.json
        c.py
        c.json
    """)

    try:
        c = cmdlets.Cmd()
        if param is not None:
            c.config_paths = [str(tdir / ff)
                              for f in param
                              for ff in f.split(os.pathsep)]
        if var is not None:
            os.environ['POLYVERS_CONFIG_PATHS'] = os.pathsep.join(
                osp.join(tdir, ff)
                for f in var
                for ff in f.split(os.pathsep))

        paths = c._collect_static_fpaths()
        paths = [P(p).relto(tdir).replace('\\', '/') for p in paths]
        assert paths == exp
    finally:
        try:
            del os.environ['POLYVERS_CONFIG_PATHS']
        except Exception as _:
            pass


def test_help_smoketest():
    cls = cmdlets.Cmd
    cls.class_get_help()
    cls.class_config_section()
    cls.class_config_rst_doc()

    c = cls()
    c.print_help()
    c.document_config_options()
    c.print_alias_help()
    c.print_flag_help()
    c.print_options()
    c.print_subcommands()
    c.print_examples()
    c.print_help()


def test_all_cmds_help_version(capsys):
    c = cmdlets.Cmd
    with pytest.raises(SystemExit):
        c.make_cmd(argv=['help'])

    ## Check cmdlet interpolations work.
    #
    out, err = capsys.readouterr()
    assert not err
    assert '{cmd_chain}' not in out
    assert '{appname}' not in out

    with pytest.raises(SystemExit):
        c.make_cmd(argv=['--help'])
    with pytest.raises(SystemExit):
        c.make_cmd(argv=['--help-all'])
    with pytest.raises(SystemExit):
        c.make_cmd(argv=['--version'])


def test_yaml_config(tmpdir):
    tdir = tmpdir.mkdir('yamlconfig')
    conf_fpath = tdir / '.polyvers.yaml'
    conf = """
    Cmd:
      verbose:
        true
    """
    with open(conf_fpath, 'wt') as fout:
        fout.write(tw.dedent(conf))

    c = cmdlets.Cmd()
    c.config_paths = [conf_fpath]
    c.initialize(argv=[])
    assert c.verbose is True


def test_Configurable_simple_yaml_generation():
    class C(trc.Configurable):
        "Class help"
        a = trt.Int(1, config=True, help="Trait help test")
        b = trt.Int(1, config=True, help="2nd trait help test")

    cfg = CommentedMap()
    C.class_config_yaml(cfg)

    ## EXPECTED
    """
        # ############################################################################
        # C(Configurable) configuration
        # ############################################################################
        # Class help
        #

        # Trait help test
        # Default: 1
          a: 1

        # 2nd trait help test
          b: 1
    """
    cfg_str = ydumps(cfg)
    #print(cfg_str)
    msgs = ['# Class help', '# Trait help test', '# 2nd trait help test',
            'a: 1', 'b: 1']
    assert all(m in cfg_str for m in msgs)


def test_Application_yaml_generation():
    class C(trc.Configurable):
        "Class help"
        a = trt.Int(1, config=True, help="Trait help test")
        b = trt.Int(1, config=True, help="2nd trait help test")

    class MyApp(trc.Application):
        classes = [C]

    cfg = MyApp().generate_config_file_yaml()

    cfg_str = ydumps(cfg)
    print(cfg_str)

    ## EXPECTED
    """
        Application:
        # ############################################################################
        # Application(SingletonConfigurable) configuration
        # ############################################################################
        # This is an application.
        #

        # The date format used by logging formatters for %(asctime)s
        # Default: '%Y-%m-%d %H:%M:%S'
          log_datefmt: '%Y-%m-%d %H:%M:%S'
        ...
        C:
        # ############################################################################
        # C(Configurable) configuration
        # ############################################################################
        # Class help
        ...
    """
    cfg_str = ydumps(cfg)
    #print(cfg_str)
    msgs = ['# Application(SingletonConfigurable) configuration',
            '# C(Configurable) configuration']
    assert all(m in cfg_str for m in msgs)


def test_Cmd_subcmd_configures_parents(tmpdir):
    tdir = tmpdir.mkdir('yamlconfig')
    tdir.chdir()

    conf_fpath = tdir / '.config.yaml'
    conf_fpath.write_text(
        "RootCmd:\n  b:\n    2\nSubCmd:\n  s:\n    -1",
        'utf-8')

    class SubCmd(cmdlets.Cmd):
        s = trt.Int(config=True)

    class RootCmd(cmdlets.Cmd):
        subcommands = {'sub': (SubCmd, "help string")}
        a = trt.Int(config=True)
        b = trt.Int(config=True)

    r = RootCmd(config=trc.Config({'Cmd': {'config_paths': ['.config']}}),
                raise_config_file_errors=True)
    r.initialize('sub --RootCmd.a=1'.split())

    assert SubCmd.instance().s == -1
    assert r.a == 1
    assert r.b == 2
