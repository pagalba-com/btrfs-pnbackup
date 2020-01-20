# Copyright (c) 2014 Marco Schindler
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the Free
# Software Foundation; either version 2 of the License, or (at your option)
# any later version.

import subprocess
import logging
import re


_logger = logging.getLogger(__name__)


def build_subprocess_args(cmd, url=None):
    """
    Create subprocess arguments for shell command/args to be executed
    Internally Wraps command into ssh call if url host name is not None
    :param cmd: Shell command string or argument list
    :param url: url of remote host
    :return: Subprocess arguments
    """
    # in case cmd is a regular value, convert to list
    cmd = cmd if isinstance(cmd, list) else [cmd]
    # wrap into bash or ssh command respectively
    # depending if command is executed locally (host==None) or remotely
    url_string = None
    ssh_args = ['ssh', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=3']

    if url is not None and url.hostname is not None:
        url_string = url.hostname
        if url.username is not None:
            url_string = '%s@%s' % (url.username, url.hostname)
            if url.username is not 'root':
                cmd[0] = re.sub(r'(?:^|\s)(mv|btrfs)\s', r' sudo backup_root \1 ', cmd[0])
        if url.port is not None:
            ssh_args += ['-p', '%s' % url.port]

    ssh_args += ['%s' % url_string]

    subprocess_args = ['bash', '-c'] + cmd if url_string is None else \
        ssh_args + cmd

    _logger.debug(subprocess_args)

    return subprocess_args


def exec_check_output(cmd, url=None) -> bytes:
    """
    Wrapper for subprocess.check_output
    :param cmd: Command text
    :param url: URL
    :return: output
    """
    return subprocess.check_output(build_subprocess_args(cmd, url), stderr=subprocess.STDOUT)


def exec_call(cmd, url=None) -> int:
    """
    Wrapper for subprocess.call
    :param cmd: Command text
    :param url: URL
    :return:
    """
    return subprocess.call(build_subprocess_args(cmd, url), stderr=subprocess.PIPE, stdout=subprocess.PIPE)


def exists(command, url=None):
    """
    Check if shell command exists
    :param command: Command to verify
    :param url: url of remote host
    :return: True if location exists, otherwise False
    """
    type_prc = subprocess.Popen(build_subprocess_args(['type ' + command], url),
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                shell=False)
    return type_prc.wait() == 0


