# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Helper tools for managing check status, outcome, and output.'''

from __future__ import absolute_import
from __future__ import print_function
import pprint
import yaml
import sys

if (sys.version_info >= (3, 3)):
    import collections.abc as abc
else:
    import collections as abc

from . import python_utils
from .python_utils import basestring, cmp
from . import exceptions as exc
from .logger import log

#: a list of reserved keywords for ResultYAML output, which can't be overridden in keyvals
RESERVED_KEYS = ('item', 'type', 'outcome',
                 'note', 'results', 'checkname',
                 'artifact', '_internal')

class CheckDetail(object):
    '''Class encompassing everything related to the outcome of a check run.
    It contains convenience methods for tracking, evaluating and reporting
    check results.

    For some checks, it's trivial to parse its output at the end of its
    execution and evaluate the results. For some, however, it's much easier
    to do this continuously during check execution. This is especially true
    for multi-item checks (a single check providing results for many items -
    builds, updates, etc). That's when this class comes very handy (it can be
    used even for the simple use cases, of course).

    :cvar tuple outcome_priority: a tuple of :attr:`outcome` keywords sorted by
                                  priority from the least important to the most
                                  important
    :ivar str item: a description the item being tested; for example a build NVR
                    (``vpnc-0.5-1.fc20``), update ID (``FEDORA-2014-3309``) or a
                    repository name (``f20-updates``)
    :ivar str report_type: a definition of the type of the object being checked;
                           for example a Koji build or a Bodhi update, The
                           allowed values are attributes in :class:`ReportType`.
                           You don't have to fill this in (or you can provide a
                           custom string value), but the reporting directives
                           react only to the known types (you can always find it
                           in ResultsDB, though).
    :ivar str outcome: a keyword specifying the final outcome of the check.
                       Available outcome keywords:

                       * PASSED - everything went well
                       * INFO - everything went well, but there is some
                         important information that needs to be pointed out
                       * FAILED - the item in question fails the check
                       * NEEDS_INSPECTION - the outcome can't be determined and
                         a manual inspection is needed
                       * ABORTED - the check aborted itself because of some
                         unexpected problems, i.e. a necessary network server is
                         not reachable. Running this check with the same
                         arguments later can help to mitigate this problem.
                       * CRASHED - the check crashed and did not provide usable
                         results

                       If no outcome has been set, this attribute returns
                       NEEDS_INSPECTION.

                       Raises :class:`CheckbValueError` if you try to assign
                       an unknown keyword.
    :ivar str note: a few words or one-sentence note about the result of
                       the check run (e.g. ``5 WARNINGS, 1 ERROR`` for an
                       rpmlint result). Should not unnecessarily duplicate
                       :attr:`item` or :attr:`outcome`, if possible.
    :ivar list output: output from the check run (a list of strings). You can easily
                       populate this by using :meth:`store`, or you can modify it
                       directly (for example filter out some messages you don't want
                       to see in the check output).
    :ivar dict keyvals: all key-value pairs in this dictionary are stored in
                        ResultsDB as 'extra data'. This can be used to store
                        e.g. a compose id or a kernel version, if that
                        information is important for querying the results. Keep
                        it as short as possible.
    :ivar str checkname: name of the check, which the CheckDetail belongs to. This
                         is usually not needed, as the check name is devised from
                         the task metadata, but if a single task produces
                         results for multiple checks, this is the way to override
                         the default behavior.
    :ivar str artifact: path to a file or directory placed in the artifacts directory,
                        either absolute ``$artifactsdir/report.html`` or relative
                        ``report.html``. It will represent task output specific for
                        this particular :attr:`item`.
    '''

    outcome_priority = ('PASSED', 'INFO', 'FAILED', 'NEEDS_INSPECTION',
                        'ABORTED', 'CRASHED')

    def __init__(self, item, report_type=None, outcome=None, note='',
                 output=None, keyvals=None, checkname=None, artifact=None):
        # validate input
        if (output is not None and
            not python_utils.sequence(output, basestring, mutable=True)):
            raise exc.CheckbValueError("'output' parameter must be a "
                "mutable sequence of strings. Yours was: %s" % type(output))
        if keyvals is not None and not isinstance(keyvals, abc.Mapping):
            raise exc.CheckbValueError("'keyvals' parameter must be a "
                    "mapping. Yours was: %s" % type(keyvals))

        self.item = item
        self.report_type = report_type
        self._outcome = None
        if outcome:
            self.outcome = outcome
        self.checkname = checkname
        self.note = note
        self.output = output or []
        self.keyvals = keyvals or {}
        self.artifact = artifact
        # this dictionary will hold implementation-specific data, that needs
        # to be transfered in between directives (like resultsdb_result_id)
        self._internal = {}


    @property
    def outcome(self):
        return self._outcome or 'NEEDS_INSPECTION'


    @outcome.setter
    def outcome(self, value):
        if value not in self.outcome_priority:
            raise exc.CheckbValueError('Unknown outcome keyword: %s' % value)
        self._outcome = value


    def update_outcome(self, outcome):
        '''Update :attr:`outcome` with the provided value only and only if it
        has a higher priority than its current value (according to
        :attr:`outcome_priority`). Otherwise this call does nothing.

        This is useful if your check performs a number of 'sub-tasks', each
        passing or failing, and you want to final outcome to be the worst/most
        serious one of those. You can just keep calling :meth:`update_outcome`
        and the highest priority outcome type will be stored at :attr:`outcome`
        at the end.

        :param str outcome: the outcome value to assign to :attr:`outcome` if it
                            has a higher priority than its current value.
                            Handles ``None`` values gracefully (no action).
        :raise CheckbValueError: if any of the outcome keywords are not
                                    specified in :attr:`outcome_priority`'''
        if self.cmp_outcome(outcome, self._outcome) > 0:
            self.outcome = outcome


    def broken(self):
        '''Tells whether the check :attr:`outcome` is set to one of the broken
        states (i.e. ABORTED or CRASHED).'''
        return self.outcome in ['ABORTED', 'CRASHED']


    def store(self, message, printout=True):
        '''Add a string to the :attr:`output`, and print it optionally as well.

        This is just a convenience method for most common use case, you can
        of course always access and modify :attr:`output` directly, and print or
        use logging facilities directly as well. This combines both into a
        single call.

        :param str message: a string to store in :attr:`output`
        :param bool printout: whether to print to standard output or not
        '''

        self.output.append(message)
        if printout:
            print(message)


    @classmethod
    def cmp_outcome(cls, outcome1, outcome2):
        '''Compare two outcomes according to :attr:`outcome_priority` and return
        -1/0/1 if ``outcome1`` has lower/equal/higher priority than ``outcome2``.

        :param str outcome1: an outcome keyword to compare
        :param str outcome2: an outcome keyword to compare
        :raise CheckbValueError: if any of the outcome keywords are not
                                    specified in :attr:`outcome_priority`
        '''

        # validate input
        for outcome in [outcome1, outcome2]:
            if (outcome not in cls.outcome_priority) and (outcome is not None):
                raise exc.CheckbValueError('Unknown outcome keyword: %s' %
                                           outcome)

        index1 = cls.outcome_priority.index(outcome1) if outcome1 is not None \
                                                      else -1
        index2 = cls.outcome_priority.index(outcome2) if outcome2 is not None \
                                                      else -1
        return cmp(index1, index2)


    @classmethod
    def create_multi_item_summary(cls, outcomes):
        '''Create a string containing a sum of all outcomes, like this:
        ``3 PASSED, 1 INFO, 2 FAILED``

        :param outcomes: either one :class:`CheckDetail` instance or an iterable
                          of :class:`CheckDetails <CheckDetail>` or an iterable
                          of :attr:`outcome` strings
        '''
        # validate input
        if isinstance(outcomes, CheckDetail):
            outcomes = (outcomes,)

        if len(outcomes) <= 0:
            return ''

        if python_utils.iterable(outcomes, CheckDetail):
            all_outcomes = [detail.outcome for detail in outcomes]
        else:  # list of strings
            if not python_utils.iterable(outcomes, basestring):
                raise exc.CheckbValueError("'outcomes' parameter type is "
                    'incorrect: %s' % type(outcomes))
            all_outcomes = outcomes

        # create the summary
        summary = []
        for res in cls.outcome_priority:
            count = all_outcomes.count(res)
            if count > 0:
                summary.append('%d %s' % (count, res))
        summary = ', '.join(summary)

        return summary


    def __str__(self):
        # Make this object more readable when printing
        # But don't show self.output, because that can be huuge
        attrs = vars(self)
        attrs['output'] = '<stripped out>'
        return '<%s: %s>' % (self.__class__.__name__, pprint.pformat(attrs))


class ReportType(object):
    ''' Enum for different types of :attr:`CheckDetail.report_type`'''
    # the values are used as identifiers in a ResultYAML export
    BODHI_UPDATE = 'bodhi_update'        #:
    COMPOSE = 'compose'                  #:
    DIST_GIT_COMMIT = 'dist_git_commit'  #:
    DOCKER_IMAGE = 'docker_image'        #:
    GIT_COMMIT = 'git_commit'            #:
    KOJI_BUILD = 'koji_build'            #:
    KOJI_TAG = 'koji_tag'                #:
    MODULE_BUILD = 'module_build'        #:
    PULL_REQUEST = 'pull_request'        #:
    # if you add a new one, please also update main.py:ITEM_TYPE_DOCS

    @classmethod
    def list(cls):
        return [cls.BODHI_UPDATE,
                cls.COMPOSE,
                cls.DIST_GIT_COMMIT,
                cls.DOCKER_IMAGE,
                cls.GIT_COMMIT,
                cls.KOJI_BUILD,
                cls.KOJI_TAG,
                cls.MODULE_BUILD,
                cls.PULL_REQUEST]


def export_YAML(check_details):
    '''Generate YAML output used for reporting to ResultsDB.

    Note: You need to provide all your :class:`CheckDetail` instances in a single pass
    in order to generate a valid YAML output. You can't call this method several
    times and then simply join the outputs simply as strings.

    :param check_details: iterable of :class:`CheckDetail` instances or single
                          instance of :class:`CheckDetail`
    :return: YAML output with results for every :class:`CheckDetail` instance
             provided
    :rtype: str
    :raise CheckbValueError: if :attr:`CheckDetail.item` or :attr:`CheckDetail.outcome`
                                is empty for any parameter provided

    Example output::

        results:
          - item: xchat-0.5-1.fc20
            type: koji_build
            outcome: PASSED
            note: 5 ERRORS, 10 WARNINGS
            artifact: xchat-0.5-1.fc20.x86_64.log
    '''

    if isinstance(check_details, CheckDetail):
        check_details = [check_details]


    # validate input
    for detail in check_details:
        if not detail.item:
            raise exc.CheckbValueError('CheckDetail.item is empty for: %s' %
                                       detail)

    results = []

    for detail in check_details:
        # Result YAML block
        data = {}
        data['item'] = detail.item
        data['outcome'] = detail.outcome
        if detail.artifact:
            data['artifact'] = detail.artifact
        if detail.report_type:
            data['type'] = detail.report_type
        if detail.note:
            data['note'] = detail.note
        if detail.checkname:
            data['checkname'] = detail.checkname
        if detail._internal:
            data['_internal'] = detail._internal
        for key, value in detail.keyvals.items():
            if key in RESERVED_KEYS:
                log.warning("Reserved key '%s' found in keyvals. Ignoring for "
                            "export purposes.", key)
                continue

            data[key] = value

        results.append(data)

    return yaml.safe_dump(
        {"results": results},
        indent=2,
        allow_unicode=True,
        default_flow_style=False
        )


def import_YAML(source):
    '''Parses YAML and returns a list of :class:`CheckDetails <CheckDetail>`.

    :param str source: YAML-formatted text
    :raise CheckbValueError: if YAML syntax is incorrect
    '''

    if not source:
        raise exc.CheckbValueError('Failed to parse YAML contents: empty input')

    try:
        data = yaml.safe_load(source)
    except yaml.scanner.ScannerError as e:
        raise exc.CheckbValueError('Failed to parse YAML contents: %s' % e)

    # check basic structure of the loaded object"
    if type(data) is not dict:
        raise exc.CheckbValueError("Invalid type of the YAML root element, %s instead of dict" %
                                   type(data))
    try:
        if type(data['results']) not in (list, type(None)):
            raise exc.CheckbValueError("Invalid type of 'results', %s instead of list" %
                                       type(data['results']))
    except KeyError:
        raise exc.CheckbValueError("Invalid format of the YAML data -"
                                      "missing `results` key")

    if data['results'] is None:
        return []

    check_details = []
    for result in data['results']:
        item = result.get('item', None)
        report_type = result.get('type', None)
        artifact = result.get('artifact', None)
        outcome = result.get('outcome', None)
        note = result.get('note', '')
        checkname = result.get('checkname', None)
        _internal = result.get('_internal', {})

        # TODO: is there a better way to do this?
        other_keys = set(result.keys()) - set(RESERVED_KEYS)
        keyvals = dict([(k, result[k]) for k in other_keys])

        cd = CheckDetail(item, report_type, outcome, note, checkname=checkname, artifact=artifact)

        cd.keyvals = keyvals
        cd._internal = _internal
        check_details.append(cd)

    return check_details
