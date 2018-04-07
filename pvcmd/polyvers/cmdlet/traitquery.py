#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2015-2018 European Commission (JRC);
# Licensed under the EUPL 1.2+ (the 'Licence');
# You may not use this work except in compliance with the Licence.
# You may obtain a copy of the Licence at: http://ec.europa.eu/idabc/eupl
#
"""
Utility to query traits of :class:`HasTraits` and build classes like `Printable`.

See query reus on :func:`select_traits()`
"""
from typing import Union, Optional, Sequence

from .._vendor import traitlets as trt


def _find_1st_mro_with_classprop(has_traits: trt.HasTraits,
                                 classprop_selector: str,
                                 ) -> Optional[trt.MetaHasTraits]:
    for cls in type(has_traits).mro():
        ptraits = vars(cls).get(classprop_selector)
        if ptraits is not None:
            return cls


def _select_traits_from_classprop(has_traits: trt.HasTraits,
                                  classprop_selector: str,
                                  first_mro_class: trt.MetaHasTraits,
                                  tnames: Union[str, Sequence, None]):
    """
    :param has_traits:
        see :meth:`select_traits()`
    :param classprop_selector:
        see :meth:`select_traits()`
    :param first_mro_class:
        the 1st baseclass of :attr:`has_traits` in `mro()` where
        a non-None class-prop named :attr:`classprop_selector` is found;
        practically, :meth:`_find_1st_mro_with_classprop()` result.
    :param tnames:
        its contents
    :raise ValueError:
        when unknown trait-names in `classprop_selector` class-property found.
    """
    if not isinstance(tnames, (list, tuple)):  # TODO: isinstance([], (). SET)
        tnames = [tnames]

    if '-' in tnames:
        tnames = [tn for tn in tnames
                  if tn != '-'] + list(first_mro_class.class_own_traits())  # type: ignore

    bads = set(tnames) - set(has_traits.traits())
    if bads:
        raise ValueError(
            "Class-property `%s.%s` contains unknown trait-names: %s" %
            (first_mro_class.__name__,
             classprop_selector, ', '.join(bads)))

    return tnames


def select_traits(has_traits: trt.HasTraits,
                  mixin: type = None,
                  classprop_selector: str = None,
                  **tag_selectors
                  ) -> Optional[Sequence[str]]:
    """
    Follow elaborate rules to select certain traits of a :class:`HasTraits` class.

    :param has_traits:
        the instance to query it's traits
    :param mixin:
        a marker-class denoting that all traits contained in classes above it
        in reverse `mro()` order must be selected.
        The default value for `classprop_selector` is formed out of
        the name of this mixin.
    :param classprop_selector:
        The name of a class-property on the `HasTraits` class to consult
        when querying traits.
        If not given but `mixin` given, it defaults to '<subclass-name>_traits'
        in lower-case,  Otherwise, or if empty-string, rule 1 bypassed.
        See "selection rules" below
    :param tag_selectors:
        Any tag-names to convey as metadata filters in :meth:`HasTraits.traits()`.
        See "selection rules" below
    :return:
        the trait-names found, or empty

    Selection rules:

    1. Scan the :attr:`classprop_selector` in ``has_traits.mro()`` and select
       class-traits according to its contents:
         - `None`/missing: ignored, visit next in `mro()`;
         - <empty-str>/<empty-seq>`: shortcut to rule 4, "no traits selected",
           below.
         - <list of trait-names>: selects them, checking for unknowns,
         - <'-' alone or contained in the list>: select ALL class's OWN traits
           in addition to any other traits contained in the list;
         - '*': select ALL traits in mro().

       But if a :attr:`classprop_selector`-named class-property is missing/`None` on
       all baseclasses, or `classprop_selector` was the empty-string...

    2. select any traits in mro() marked with :attr:`tag_selectors` metadata.

       And if none found...

    3. select all traits owned by classes contained in revese `mro()` order
       from the 1st baseclass inheriting :attr:`mixin`  and uppwards.

       And if no traits found, ...

    4. don't select any traits.
    """
    if mixin:
        if not isinstance(has_traits, mixin):
            raise ValueError(
                "Mixin '%s' is not a subclass of queried '%s'!" %
                (mixin, has_traits))

        sbcname = mixin.__name__.lower()
        if classprop_selector is None:
            classprop_selector = '%s_traits' % sbcname

    ## rule 1: select based on traitnames in class-property.
    #
    if classprop_selector:
        class_tnames = getattr(has_traits, classprop_selector, None)
        if class_tnames == '*':
            return has_traits.traits()
        elif class_tnames:
            subclass = _find_1st_mro_with_classprop(has_traits, classprop_selector)
            assert subclass, (subclass, has_traits, classprop_selector)
            return _select_traits_from_classprop(has_traits, classprop_selector,
                                                 subclass, class_tnames)
        elif not class_tnames and class_tnames is not None:
            ## If empty, shortcut to "no traits selected".
            return ()

    ## rule 2: select based on trait-tags
    tnames = has_traits.traits(**tag_selectors)

    ## rule 3: Select all traits for subclasses
    #  after(above) `mixin` in mro().
    #
    if not tnames and mixin:
        subclasses = [cls for cls in type(has_traits).mro()  # type: ignore
                      if issubclass(cls, mixin) and
                      cls is not mixin]
        tnames = [tname
                  for cls in subclasses
                  for tname in cls.class_own_traits()]  # type: ignore

    return tnames or ()
