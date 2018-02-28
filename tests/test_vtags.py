#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2015-2018 European Commission (JRC);
# Licensed under the EUPL 1.2+ (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl

from polyvers import vtags
from polyvers import polyverslib

import pytest

import subprocess as sbp
import sys


proj1 = 'proj1'
proj1_desc = 'proj1-v0.0.1-2-g'
proj2 = 'proj-2'
proj2_desc = 'proj-2-v0.2.1'


def test_get_all_vtags(ok_repo, untagged_repo, no_repo):
    ok_repo.chdir()

    v = vtags.find_all_subproject_vtags()
    assert dict(v) == {
        proj1: ['0.0.0', '0.0.1'],
        proj2: ['0.2.0', '0.2.1'],
    }
    untagged_repo.chdir()

    v = vtags.find_all_subproject_vtags()
    assert dict(v) == {}

    no_repo.chdir()

    with pytest.raises(sbp.CalledProcessError):
        v = vtags.find_all_subproject_vtags()


def test_get_p1_vtags(ok_repo, untagged_repo, no_repo):
    ok_repo.chdir()

    v = vtags.find_all_subproject_vtags(proj1)
    assert dict(v) == {proj1: ['0.0.0', '0.0.1']}
    untagged_repo.chdir()

    v = vtags.find_all_subproject_vtags(proj1)
    assert dict(v) == {}

    no_repo.chdir()

    with pytest.raises(sbp.CalledProcessError):
        v = vtags.find_all_subproject_vtags(proj1)


def test_get_p2_vtags(ok_repo):
    ok_repo.chdir()
    v = vtags.find_all_subproject_vtags(proj2)
    assert dict(v) == {proj2: ['0.2.0', '0.2.1']}


def test_get_BAD_project_vtag(ok_repo, untagged_repo, no_repo):
    ok_repo.chdir()

    v = vtags.find_all_subproject_vtags('foo')
    assert dict(v) == {}
    v = vtags.find_all_subproject_vtags('foo', proj1)
    assert dict(v) == {proj1: ['0.0.0', '0.0.1']}

    untagged_repo.chdir()

    v = vtags.find_all_subproject_vtags('foo', 'bar')
    assert dict(v) == {}
    no_repo.chdir()

    with pytest.raises(sbp.CalledProcessError):
        v = vtags.find_all_subproject_vtags('foo')


def test_get_subproject_versions(ok_repo, untagged_repo, no_repo):
    ok_repo.chdir()

    v = vtags.get_subproject_versions()
    assert v == {
        proj1: '0.0.1',
        proj2: '0.2.1',
    }
    untagged_repo.chdir()

    v = vtags.get_subproject_versions()
    assert v == {}

    no_repo.chdir()

    with pytest.raises(sbp.CalledProcessError):
        v = vtags.get_subproject_versions()

    with pytest.raises(sbp.CalledProcessError):
        v = vtags.get_subproject_versions('foo')

    with pytest.raises(sbp.CalledProcessError):
        v = vtags.get_subproject_versions('foo' 'bar')


def test_get_BAD_projects_versions(ok_repo):
    ok_repo.chdir()
    v = vtags.get_subproject_versions('foo')
    assert dict(v) == {}


##############
## DESCRIBE ##
##############

def rfc2822_today():
    ## TCs may fail if run when day changes :-)
    return polyverslib.rfc2822_tstamp()[:12]  # till hour


def test_git_describe_p1(ok_repo, untagged_repo, no_repo):
    ok_repo.chdir()

    v = vtags.git_describe(proj1,)
    assert v.startswith(proj1_desc)

    untagged_repo.chdir()

    with pytest.raises(vtags.GitVoidError):
        v = vtags.git_describe('foo')

    no_repo.chdir()

    with pytest.raises(vtags.GitVoidError):
        vtags.git_describe(proj1)


def test_git_describe_p2(ok_repo):
    ok_repo.chdir()

    v = vtags.git_describe(proj2)
    assert v == proj2_desc


def test_git_describe_BAD(ok_repo, untagged_repo, no_repo):
    ok_repo.chdir()

    with pytest.raises(vtags.GitVoidError):
        vtags.git_describe('foo')


@pytest.mark.skipif(sys.version_info < (3, ),
                    reason="FileNotFoundError not in PY27, OSError only.")
def test_git_describe_BAD_no_git_cmd(ok_repo, monkeypatch):
    ok_repo.chdir()
    monkeypatch.setenv('PATH', '')

    with pytest.raises(FileNotFoundError):
        vtags.git_describe('foo')


def test_last_commit_tstamp_p1(ok_repo, untagged_repo, no_repo):
    ok_repo.chdir()

    d = vtags.last_commit_tstamp()
    assert d.startswith(rfc2822_today())

    untagged_repo.chdir()

    d = vtags.last_commit_tstamp()
    assert d.startswith(rfc2822_today())

    no_repo.chdir()

    with pytest.raises(vtags.GitVoidError):
        vtags.last_commit_tstamp()


def test_last_commit_tstamp_BAD_no_commits(empty_repo):
    empty_repo.chdir()

    with pytest.raises(vtags.GitVoidError):
        vtags.last_commit_tstamp()


@pytest.mark.skipif(sys.version_info < (3, ),
                    reason="FileNotFoundError not in PY27, OSError only.")
def test_last_commit_tstamp_BAD_no_git_cmd(ok_repo, monkeypatch):
    ok_repo.chdir()
    monkeypatch.setenv('PATH', '')

    with pytest.raises(FileNotFoundError):
        vtags.last_commit_tstamp()
