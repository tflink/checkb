# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

from __future__ import absolute_import
import os
import sys

import requests
from requests.packages.urllib3.util.retry import Retry
import progressbar

from checkb.logger import log
from checkb.exceptions import CheckbRemoteError


REQUESTS_MAX_RETRIES = 5
REQUESTS_STATUS_RETRY = list(range(500, 512))
REQUESTS_TIMEOUT = 30
REQUESTS_CHUNK_SIZE = 1024 * 1024  # 1 MB
_requests_session = None


def _get_session(max_retries=REQUESTS_MAX_RETRIES,
    status_retry=REQUESTS_STATUS_RETRY):
    """Note that a singleton is returned and so the configuration is performed
    only the first time this functions is called.
    """
    global _requests_session
    if not _requests_session:
        _requests_session = requests.Session()
        retries = Retry(total=max_retries, backoff_factor=2,
            status_forcelist=status_retry,
            # needed if we want to determine last request status code
            # https://stackoverflow.com/a/43496895
            raise_on_status=False)
        _requests_session.mount('http://',
            requests.adapters.HTTPAdapter(max_retries=retries))
        _requests_session.mount('https://',
            requests.adapters.HTTPAdapter(max_retries=retries))

    return _requests_session


def makedirs(fullpath):
    '''This is the same as :meth:`os.makedirs`, but does not raise an exception
    when the destination directory already exists.

    :raise OSError: if directory doesn't exist and can't be created
    '''
    try:
        os.makedirs(fullpath)
        assert os.path.isdir(fullpath)
    except OSError as e:
        if e.errno == 17: # "[Errno 17] File exists"
            # if it is a directory everything is ok
            if os.path.isdir(fullpath):
                return
            # otherwise it is a file/socket/etc and it is an error
            else:
                log.warning("Can't create directory, something else already exists: %s",
                            fullpath)
                raise
        else:
            log.warning("Can't create directory: %s", fullpath)
            raise


def _same_length(filepath, url):
    '''Determine whether a local file and a file referred by HTTP URL have the
    same length. If any exception occurs, ``False`` is returned.
    :rtype: bool
    '''
    try:
        local_size = os.path.getsize(filepath)

        response = _get_session().head(url, timeout=REQUESTS_TIMEOUT,
            allow_redirects=True)
        response.raise_for_status()
        remote_size = int(response.headers.get('Content-Length'))

        return local_size == remote_size
    except:
        return False


def download(url, dirname, filename=None, cachedir=None):
    '''Download a file.

    :param str url: file URL to download
    :param str dirname:  directory path; if the directory does not exist, it gets
                         created (and all its parent directories).
    :param str filename: name of downloaded file; if not provided, the basename
                         is extracted from URL
    :param str cachedir: If set, the file will be downloaded to a cache
                         directory specified by this parameter. If the file is
                         already present and of the same length, download is skipped.
                         The requested destination file (``dirname/filename``)
                         will be a symlink to the cached file.
                         This directory is automatically created if not present.
    :return: the path to the downloaded file
    :rtype: str
    :raise CheckbRemoteError: if download fails
    '''

    if not filename:
        filename = os.path.basename(url)

    dl_dest = dest = os.path.abspath(os.path.join(dirname, filename))
    dirs_to_create = [dirname]

    if cachedir:
        dl_dest = os.path.join(cachedir, filename)
        dirs_to_create.append(cachedir)

    for directory in dirs_to_create:
        makedirs(directory)

    # check file existence and validity
    download = True
    if os.path.exists(dl_dest):
        if _same_length(dl_dest, url):
            log.debug('Already downloaded: %s', dl_dest)
            download = False
        else:
            log.debug('Cached file %s differs from its online version. '
                      'Redownloading.', dl_dest)

    # download the file
    if download:
        log.debug('Downloading%s: %s', ' (cached)' if cachedir else '', url)
        try:
            _download(url, dl_dest)
        except requests.exceptions.RequestException as e:
            log.debug('Download failed: %s', e)
            # the file can be incomplete, remove
            if os.path.exists(dl_dest):
                try:
                    os.remove(dl_dest)
                except OSError:
                    log.warning('Could not delete incomplete file: %s', dl_dest)

            raise CheckbRemoteError(e, errno=e.response.status_code)

    # create a symlink if the download was cached
    if cachedir:
        try:
            if os.path.exists(dest):
                # if there already is something at the destination, we need to
                # remove it first
                os.remove(dest)
            os.symlink(dl_dest, dest)
        except OSError:
            log.exception("Can't create symlink %s -> %s", dl_dest, dest)
            raise

    return dest


def _download(url, dest, timeout=REQUESTS_TIMEOUT, chunk_size=REQUESTS_CHUNK_SIZE):
    """
    A download helper function.

    :param str url: an url to be downloaded
    :param str dest: a destination of the downloaded file
    :param float timeout: how long to wait for the server to send data before giving up
    :param int chunk_size: chunk size of the file downloaded (loaded into memory) at a time
    :raise requests.exceptions.RequestException: if the download request failed
    """

    r = _get_session().get(url, timeout=timeout, stream=True)

    # if there was a download error (HTTP 4xx or 5xx), raise an error
    r.raise_for_status()

    with open(dest, 'wb') as f:
        total_len = r.headers.get('Content-Length')

        if total_len is None:
            for chunk in r.iter_content(chunk_size):
                # filter out keep-alive new lines
                if chunk:
                    f.write(chunk)
        else:
            widgets = [progressbar.Percentage(), progressbar.Bar(), progressbar.ETA(),
                       progressbar.FileTransferSpeed()]

            # Determine if we are using progressbar or progressbar2
            if hasattr(progressbar.ProgressBar(), 'max_value'):
                pbar = progressbar.ProgressBar(widgets=widgets, max_value=int(total_len)).start()
            else:
                pbar = progressbar.ProgressBar(widgets=widgets, maxval=int(total_len)).start()

            read = 0
            for chunk in r.iter_content(chunk_size):
                # filter out keep-alive new lines
                if chunk:
                    f.write(chunk)
                    # chunk can be smaller than chunk_size (end of file) or larger than it (content
                    # decompression)
                    read += min(len(chunk), chunk_size)
                    # don't exceed pbar.maxval/pbar.max_value, which can happen due to content
                    # decompression (see T755). This should not occur except for the last chunk.
                    if hasattr(progressbar.ProgressBar(), 'max_value'):
                        pbar.update(min(read, pbar.max_value))
                    else:
                        pbar.update(min(read, pbar.maxval))


# http://stackoverflow.com/questions/11325019
class Tee(object):
    '''Helper class for writing data to different streams.'''

    def __init__(self, *files):
        self._files = list(files)

    def add(self, file_):
        if file_.mode.startswith('w'):
            self._files.append(file_)
        else:
            name = file_.name if hasattr(file_, 'name') else '<unnamed file>'
            log.warning('File %s not opened for writing. Not adding.', name)

    def write(self, data):
        for f in self._files:
            f.write(data)

    def close(self):
        for f in self._files:
            if f is not sys.stdout:
                f.close()
