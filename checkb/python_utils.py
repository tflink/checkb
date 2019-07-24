# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''A collection of convenience methods related to Python base libraries.'''

from __future__ import absolute_import
import sys

if (sys.version_info >= (3, 3)):
    import collections.abc as abc
else:
    import collections as abc

import checkb.exceptions as exc

try:
    # Python 2
    basestring = basestring
except NameError:
    # Python 3
    basestring = str

def iterable(obj, item_type=None):
    '''Decide whether ``obj`` is an :class:`~collections.abc.Iterable` (you can
    traverse through its elements - e.g. ``list``, ``tuple``, ``set``, even
    ``dict``), but not ``basestring`` (which satisfies most collections'
    requirements, but we don't often want to consider as a collection). You can
    also verify the types of items in the collection.

    :param any obj: any object you want to check
    :param type item_type: all items in ``obj`` must be instances of this
                           provided type. If ``None``, no check is performed.
    :return: whether ``obj`` is iterable but not a string, and whether ``obj``
                     contains only ``item_type`` items
    :rtype: bool
    :raise CheckbValueError: if you provide invalid parameter value
    '''
    return _collection_of(obj, abc.Iterable, item_type)


def sequence(obj, item_type=None, mutable=False):
    '''This has the same functionality and basic arguments as :func:`iterable`
    (read its documentation), but decides whether ``obj`` is a
    :class:`~collections.abc.Sequence` (ordered and indexable collection - e.g.
    ``list`` or ``tuple``, but not ``set`` or ``dict``).

    :param bool mutable: if ``True``, the ``obj`` must be a mutable sequence
                         (e.g. ``list``, but not ``tuple``)
    '''
    col = abc.MutableSequence if mutable else abc.Sequence
    return _collection_of(obj, col, item_type)


def _collection_of(obj, collection_cls, item_type=None):
    '''The same as :func:`iterable` or :func:`sequence`, but the abstract
    collection class can be specified dynamically with ``collection_cls``.
    '''
    if not isinstance(obj, collection_cls) or isinstance(obj, basestring):
        return False

    if item_type is not None and isinstance(obj, abc.Iterable):
        try:
            return all([isinstance(item, item_type) for item in obj])
        except TypeError as e:
            raise exc.CheckbValueError("'item_type' must be a type definition, not '%r': %s" %
                                       (item_type, e))

    return True


def reverse_argparse(args, ignore=()):
    '''Take cmdline arguments parsed by :mod:`argparse` and revert it back to a command line.

    | Example input: ``{item: 'foo', debug: True, arch: ['x86_64', 'i386'], job_id: 1234,
                        t: 'koji'}``
    | Example output: ``['--item', 'foo', '--debug', '--arch', 'x86_64', '--arch', 'i386',
                         '--job-id', '1234', '-t', 'koji']``

    This is a very naive implementation and has several limitations:

    * You should put positional arg names into the ignore list. Handling those is not implemented
      because we don't need them.
    * All options need to use ``action='store'``, ``action='store_true'`` or ``action='append'``.
      Nothing else is supported. If you use some other actions, you need to put those options into
      the ignore list.
    * All multi-word options names will be assumed to be using dashes as a separator. Be sure you
      do not use underscores, or convert it accordingly yourself.

    :param dict args: arguments parsed from :mod:`argparse` converted to a ``dict``. This is what
                      you get by running ``vars(parser.parse_args())``.
    :param ignore: list of option names which should be ignored. If you use any positional
                   arguments, you need to include their variables names here as well. The ignore
                   list is checked before the underscore-to-dash conversion takes place.
    :type ignore: list of str
    :return: reversed command line as a list of strings. Please note the returned strings are not
             shell-escaped. Be sure to do that if you run it in a shell mode.
    :rtype: list of str
    '''
    cmdline = []

    for name, value in sorted(args.items()):
        if name in ignore:
            continue

        segment = []

        # argparse converts all dashes to underscores when creating variable names, change it back
        name = name.replace('_', '-')

        opt_name = '-' if len(name) == 1 else '--'  # support both short and long options
        opt_name += name

        if value is None:  # this means the option was not present on cmdline
            continue
        if type(value) is bool:
            if value:
                # we support only action=store_true, therefore default value is False, and True
                # means the option was present
                segment.append(opt_name)
        elif sequence(value):
            for item in value:
                segment.extend((opt_name, str(item)))
        else:
            segment.extend((opt_name, str(value)))

        cmdline.extend(segment)

    return cmdline


def cmp(x, y):
    """
    Replacement for built-in function cmp that was removed in Python 3

    Compare the two objects x and y and return an integer according to
    the outcome. The return value is negative if x < y, zero if x == y
    and strictly positive if x > y.

    https://portingguide.readthedocs.io/en/latest/comparisons.html#the-cmp-function
    """

    return (x > y) - (x < y)
