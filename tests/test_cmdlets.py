#! python
# -*- coding: UTF-8 -*-
#
# Copyright 2015-2017 European Commission (JRC);
# Licensed under the EUPL (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl

import logging
from os import pathsep as PS
import os
from polyvers import cmdlets as cmd
from polyvers._vendor import traitlets as trt
from polyvers._vendor.traitlets import Int  # @UnresolvedImport
from polyvers.logconfutils import init_logging
import tempfile

import pytest

import os.path as osp
from py.path import local as P  # @UnresolvedImport
import textwrap as tw

from .conftest import touchpaths


init_logging(level=logging.DEBUG, logconf_files=[])

log = logging.getLogger(__name__)

mydir = osp.dirname(__file__)


def test_Replaceable():
    class C(trt.HasTraits, cmd.Replaceable):
        a = Int()

    c = C(a=1)
    cc = c.replace(a=2)

    assert c.a == 1
    assert cc.a == 2


def test_CfgFilesRegistry_consolidate_posix_1():
    visited = [
        ('/d/foo/bar/.appname', None),
        ('/d/foo/bar/.appname', 'appname_config.py'),
        ('/d/foo/bar/.appname', 'appname_config.json'),
        ('/d/foo\Bar/dooba/doo', None),
        ('/d/foo\Bar/dooba/doo', None),
        ('/d/foo\Bar/dooba/doo', None),
        ('/d/foo\Bar/dooba/doo', None),
    ]
    c = cmd.CfgFilesRegistry()
    cons = c._consolidate(visited)

    exp = [
        ('/d/foo/bar/.appname', ['appname_config.py', 'appname_config.json']),
        ('/d/foo\Bar/dooba/doo', []),
    ]
    #print('FF\n', cons)
    assert cons == exp


def test_CfgFilesRegistry_consolidate_posix_2():
    visited = [
        ('/c/Big/BEAR/.appname', 'appname_persist.json'),
        ('/c/Big/BEAR/.appname', 'appname_config.py'),
        ('/c/Big/BEAR/.appname', None),
        ('/d/foo\Bar/dooba/doo', None),
        ('/d/foo\Bar/dooba/doo', None),
        ('/d/foo\Bar/dooba/doo', None),
        ('/d/foo\Bar/dooba/doo', None),
    ]
    c = cmd.CfgFilesRegistry()
    cons = c._consolidate(visited)

    exp = [
        ('/c/Big/BEAR/.appname', ['appname_persist.json', 'appname_config.py']),
        ('/d/foo\Bar/dooba/doo', []),
    ]
    #print('FF\n', cons)
    assert cons == exp


def test_CfgFilesRegistry_consolidate_win_1():
    visited = [
        ('D:\\foo\\bar\\.appname', None),
        ('D:\\foo\\bar\\.appname', 'appname_config.py'),
        ('D:\\foo\\bar\\.appname', 'appname_config.json'),
        ('d:\\foo\Bar\\dooba\\doo', None),
        ('d:\\foo\Bar\\dooba\\doo', None),
        ('d:\\foo\Bar\\dooba\\doo', None),
        ('d:\\foo\Bar\\dooba\\doo', None),
    ]
    c = cmd.CfgFilesRegistry()
    cons = c._consolidate(visited)

    exp = [
        ('D:\\foo\\bar\\.appname', ['appname_config.py', 'appname_config.json']),
        ('d:\\foo\Bar\\dooba\\doo', []),
    ]
    #print('FF\n', cons)
    assert cons == exp


def test_CfgFilesRegistry_consolidate_win_2():
    visited = [
        ('C:\\Big\\BEAR\\.appname', 'appname_persist.json'),
        ('C:\\Big\\BEAR\\.appname', 'appname_config.py'),
        ('C:\\Big\\BEAR\\.appname', None),
        ('D:\\foo\Bar\\dooba\\doo', None),
        ('D:\\foo\Bar\\dooba\\doo', None),
        ('D:\\foo\Bar\\dooba\\doo', None),
        ('D:\\foo\Bar\\dooba\\doo', None),
    ]
    c = cmd.CfgFilesRegistry()
    cons = c._consolidate(visited)

    exp = [
        ('C:\\Big\\BEAR\\.appname', ['appname_persist.json', 'appname_config.py']),
        ('D:\\foo\Bar\\dooba\\doo', []),
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

    cfr = cmd.CfgFilesRegistry()
    fpaths = cfr.collect_fpaths(['conf'])
    fpaths = [P(p).relto(tdir).replace('\\', '/') for p in fpaths]
    assert fpaths == 'conf.json conf.py conf.d/a.json conf.d/a.py'.split()

    cfr = cmd.CfgFilesRegistry()
    fpaths = cfr.collect_fpaths(['conf.py'])
    fpaths = [P(p).relto(tdir).replace('\\', '/') for p in fpaths]
    assert fpaths == 'conf.py conf.py.d/a.json conf.d/a.json conf.d/a.py'.split()


def test_no_default_config_paths(tmpdir):
    cwd = tmpdir.mkdir('cwd')
    cwd.chdir()

    home = tmpdir.mkdir('home')
    os.environ['HOME'] = str(home)

    c = cmd.Cmd()
    c.initialize([])
    print(c._cfgfiles_registry.config_tuples)
    assert len(c.loaded_config_files) == 0


def test_default_loaded_paths():
    with tempfile.TemporaryDirectory(prefix=__name__) as tdir:
        class MyCmd(cmd.Cmd):
            ""
            @trt.default('config_paths')
            def _config_paths(self):
                return [tdir]

        c = MyCmd()
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
        p = cmd.PathList()

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
        c = cmd.Cmd()
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
    cls = cmd.Cmd
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

    c = cmd.Cmd()
    c.config_paths = [conf_fpath]
    c.initialize(argv=[])
    assert c.verbose is True
