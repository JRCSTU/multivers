#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2015-2018 European Commission (JRC);
# Licensed under the EUPL 1.2+ (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl
#
"""YAML utils."""
#: YAML dumper used e.g. to serialize command's outputs.

from _collections import defaultdict, OrderedDict as odict
from typing import Optional
import io
import pathlib

import contextvars as cv
import textwrap as tw

from .._vendor import traitlets as trt


_dump_trait_help = cv.ContextVar('dump_trait_help')
_classes_yamling = cv.ContextVar('classes_yamling')


def _make_trait_help(has_traits, trait):
    from ipython_genutils.text import wrap_paragraphs

    classes = _classes_yamling.get()
    cls = type(has_traits)

    if classes:
        defining_class = cls._defining_class(trait, classes)
    else:
        defining_class = cls
    if defining_class is cls:
        help_lines = ['',
                      '%s %s %s' % ('#' * 4, trait.name, '#' * 4)]
        help_lines.extend(wrap_paragraphs(trait.help, 78))
        help_lines.append('Type: ' + trait.info())
        if 'Enum' in type(trait).__name__:
            help_lines.append('Choices: %s' % trait.info())

        default_value = trait.default()
        if default_value:
            default_repr = ydumps(trait.default(), trait_help=False)
            if default_repr.count('\n') > 1 and default_repr[0] != '\n':
                default_repr = tw.indent('\n' + default_repr, ' ' * 9)
            help_lines.append('Default: %s' % default_repr)
    else:
        # Trait appears multiple times and isn't defined here.
        # Truncate help to first line + "See also Original.trait"
        if trait.help:
            help_lines.append(trait.help.split('\n', 1)[0])
        help_lines.append('See also: %s.%s' % (defining_class.__name__, trait.name))

    return '\n'.join(help_lines)


def _preserve_any_literals(v):
    from ruamel.yaml import scalarstring as scs

    if isinstance(v, str) and '\n' in v:
        return scs.preserve_literal(tw.dedent(v.replace('\r\n', '\n')
                                              .replace('\r', '\n'))
                                    .strip())
    return v


class YAMLable(metaclass=trt.MetaHasTraits):
    """A `HasTraits` mixin to denote to yaml-representer to dump all traits as dict values."""
    @staticmethod
    def _YAML_represent_instance(dumper, has_traits):
        from ..cmdlet import traitquery
        from ruamel.yaml import comments

        traits = traitquery.select_traits(has_traits, YAMLable,
                                          config=True)
        #cls_name = getattr(has_traits, 'name', type(has_traits).__name__)
        ddict = {tname: _preserve_any_literals(getattr(has_traits, tname))
                 for tname, trait in traits.items()}

        if _dump_trait_help.get():
            ddict = comments.CommentedMap((tname, tvalue)
                                          for tname, tvalue in ddict.items()
                                          if tvalue != traits[tname].default())

            for tname, trait in traits.items():
                ddict.yaml_set_comment_before_after_key(
                    tname, before=_make_trait_help(has_traits, trait))

        return _get_yamel().representer.represent_dict(ddict)


def _get_yamel():
    from ruamel import yaml
    from ruamel.yaml.representer import RoundTripRepresenter

    def _represent_path(_dumper, path):
        return y.representer.represent_str(str(path))

    y = yaml.YAML(typ='rt')

    yaddrepr = y.representer
    for d in [odict, defaultdict]:
        yaddrepr.add_representer(d, RoundTripRepresenter.represent_dict)

    yaddrepr.add_multi_representer(pathlib.Path, _represent_path)
    yaddrepr.add_multi_representer(YAMLable, YAMLable._YAML_represent_instance)

    return y


def ydumps(obj, sink=None, trait_help=False, classes=()) -> Optional[str]:
    """
    Dump any false objects as empty string, None as nothing, or as YAML.

    :param classes:
        The list of other classes to be YAMLed, to consider for redundancy.
        Will return `cls` even if it is not defined on `cls`
        if the defining class is not in `classes`.

        See also: :meth:`~Configurable._defining_class()`
    """

    if not obj:
        if sink:
            sink.write('')
            return  # type: ignore
        return ''

    def dump_with_contextvars():
        _dump_trait_help.set(trait_help)
        _classes_yamling.set(classes)

        _get_yamel().dump(obj, sink)

    dump_to_str = not bool(sink)
    if dump_to_str:
        sink = io.StringIO()

    cv.Context().run(dump_with_contextvars)

    if dump_to_str:
        return sink.getvalue().strip()


def yloads(text):
    "Dump any false objects as empty string, None as nothing, or as YAML. "

    if not text:
        return

    return _get_yamel().load(text)
