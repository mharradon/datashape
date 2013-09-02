# -*- coding: utf-8 -*-

"""
This module implements type coercion rules for data shapes.

Note that transitive coercions could be supported, but we decide not to since
it may involve calling a whole bunch of functions with a whole bunch of types
to figure out whether this is possible in the face of polymorphic overloads.
"""

from functools import partial
from collections import defaultdict
from itertools import chain, product

from blaze import error
from .coretypes import CType, TypeVar
from .traits import *
from . import verify, normalize, Implements, Fixed, Ellipsis

class CoercionTable(object):
    """Table to hold coercion rules"""

    def __init__(self):
        self.table = {}
        self.srcs = defaultdict(set)
        self.dsts = defaultdict(set)

    def add_coercion(self, src, dst, cost, transitive=True):
        """
        Add a coercion rule
        """
        if (src, dst) not in self.table:
            self.table[src, dst] = cost
            self.srcs[dst].add(src)
            self.dsts[src].add(dst)
            reflexivity(src, self)
            reflexivity(dst, self)
            if transitive:
                transitivity(src, dst, self)

    def coercion_cost(self, src, dst):
        """
        Determine a coercion cost for coercing type `a` to type `b`
        """
        return self.table[src, dst]


_table = CoercionTable()
add_coercion = _table.add_coercion
coercion_cost = _table.coercion_cost

#------------------------------------------------------------------------
# Coercion function
#------------------------------------------------------------------------

def coerce(a, b, normalized=None, seen=None):
    """
    Determine a coercion cost from type `a` to type `b`.

    Type `a` and `b'` must be unifyable and normalized.
    """
    # TODO: Cost functions for conversion between type constructors in the
    # lattice (implement a "type join")
    if seen is None:
        seen = set()
    if not normalized:
        normalized, _ = normalize([(a, b)], [True])

    return sum([_coerce(x, y, seen) for x, y in normalized])

def _coerce(a, b, seen=None):
    if isinstance(a, TypeVar):
        # Note; don't match this with 'a == b', since we need to verify atoms
        # even if equal (e.g. (..., ...) returns -1)
        return 0
    elif isinstance(a, CType) and isinstance(b, CType):
        try:
            return coercion_cost(a, b)
        except KeyError:
            raise error.CoercionError(a, b)
    elif isinstance(b, TypeVar):
        visited = b not in seen
        seen.add(b)
        return 0.1 * visited
    elif isinstance(b, Implements):
        if a in b.typeset:
            return 1 - (1.0 / len(b.typeset.types))
        else:
            raise error.CoercionError(a, b)
    elif isinstance(b, Fixed):
        assert isinstance(a, Fixed) and a.val in (1, b.val)
        if a.val != b.val:
            return 0.1 # broadcasting penalty
        return 0
    elif isinstance(a, Ellipsis) and isinstance(b, Ellipsis):
        # If we throw in an ellipsis without any constraints, then we should
        # coerce to something that accepts an arbitrary number of dimensions
        return -1
    else:
        verify(a, b)
        return sum(_coerce(x, y, seen) for x, y in zip(a.parameters, b.parameters))

#------------------------------------------------------------------------
# Coercion invariants
#------------------------------------------------------------------------

def reflexivity(a, table=_table):
    """Enforce coercion rule reflexivity"""
    if (a, a) not in table.table:
        table.add_coercion(a, a, 0)

def transitivity(a, b, table=_table):
    """Enforce coercion rule transitivity"""
    # (src, a) ∈ R and (a, b) ∈ R => (src, b) ∈ R
    for src in table.srcs[a]:
        table.add_coercion(src, b, table.coercion_cost(src, a) +
                                   table.coercion_cost(a, b))

    # (a, b) ∈ R and (b, dst) ∈ R => (a, dst) ∈ R
    for dst in table.dsts[b]:
        table.add_coercion(a, dst, table.coercion_cost(a, b) +
                                   table.coercion_cost(b, dst))

#------------------------------------------------------------------------
# Default coercion rules
#------------------------------------------------------------------------

_order = list(chain(boolean, integral, floating, complexes))

def add_numeric_rule(typeset1, typeset2, transitive=True):
    for a, b in product(typeset1, typeset2):
        if a.itemsize <= b.itemsize:
            cost = _order.index(b) - _order.index(a)
            add_coercion(a, b, cost, transitive=transitive)

add_numeric_rule(integral, integral)
add_numeric_rule(floating, floating)
add_numeric_rule(complexes, complexes)

add_numeric_rule(boolean, signed, transitive=False)
add_numeric_rule(unsigned, signed)
add_numeric_rule(integral, floating)
add_numeric_rule(floating, complexes)