#! python
# -*- coding: UTF-8 -*-
#
# Copyright 2015-2017 European Commission (JRC);
# Licensed under the EUPL (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl

from polyvers._vendor.traitlets import traitlets as trt


def test_traitlets_recurse():
    stack = trt.Tuple(trt.Int(), trt.List())
    stack._traits[1]._trait = stack

    ## Class definition will crash if not recursion broken!
    class C(trt.HasTraits):
        t = stack

    c = C()
    c.t = (1, [])
    assert c.t == (1, [])

    c = C(t=(1, []))
    assert c.t == (1, [])

    c.t[1].append((22, []))
    c.t[1].append((33, []))
    assert c.t == (1, [(22, []), (33, [])])

    c = C(t=(1, [(22, [(333, [])])]))
    assert c.t == (1, [(22, [(333, [])])])
