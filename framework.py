# -*- coding: utf-8 -*-
"""
Created on 2013-4-13

@author: seven
"""

import os
import signal
import sys
import tempfile


def _tmp():
    return tempfile.gettempdir()


def _pid(p):
    return '{}/{}.pid'.format(_tmp(), p)


def setPid(prog):
    fn = _pid(prog)
    fpid = open(fn, 'w', 0)
    try:
        fpid.write(str(os.getpid()))
    except IOError:
        raise sys.stderr.write('Error write pid file:' + fn)
    fpid.close()


def unsetPid(prog):
    fn = _pid(prog)
    if os.path.isfile(fn):
        try:
            print ('rm pid: {}'.format(fn))
            print (os.subprocess.getoutput('rm -rf {}'.format(fn)))
        except IOError:
            raise sys.stderr.write('Error rm pid file: {}'.format(fn))


def getPid(prog):
    fn = _pid(prog)
    if not os.path.isfile(fn):
        return None
    pid = None
    fpid = open(fn, 'r')
    try:
        pid = fpid.read()
    except IOError:
        pass
    fpid.close()
    return pid


def daemonize():
    # Perform 1st fork
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError:
        sys.exit(1)

    # system call
    os.chdir("/")
    os.umask(0)
    os.setsid()

    # 2nd fork
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError:
        sys.exit(1)

    # now it's a daemonize
    for f in sys.stdout, sys.stderr: f.flush()
    si = file('/dev/null', 'r')
    so = file('/dev/null', 'a+', 0)
    se = file('/dev/null', 'a+', 0)
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())


class Console(object):
    _bToClose = False

    def __init__(self):
        self._init_signal_handler()

    def _init_signal_handler(self):
        signal.signal(signal.SIGTTOU, signal.SIG_IGN)
        signal.signal(signal.SIGTTIN, signal.SIG_IGN)
        signal.signal(signal.SIGTSTP, signal.SIG_IGN)
        signal.signal(signal.SIGALRM, signal.SIG_IGN)
        signal.signal(signal.SIGPIPE, signal.SIG_IGN)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        if __debug__:
            print ('signum: {}'.format(signum))
            print ('frame: {}'.format(frame))

            if signum == signal.SIGINT or signum == signal.SIGTERM:
                self._bToClose = True
            print ('To close : {}'.format(self._bToClose))

    def isToClose(self):
        return self._bToClose


class Singleton(type):
    """Sigleton Metaclass"""

    def __init__(cls, name, bases, dic):
        super(Singleton, cls).__init__(name, bases, dic)
        cls.instance = None

    def __call__(self, *args, **kwargs):
        if self.instance is None:
            self.instance = super(Singleton, self).__call__(*args, **kwargs)
        return self.instance
