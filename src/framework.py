# -*- coding: utf-8 -*-
'''
Created on 2013-4-13

@author: seven
'''
import sys
import os
import signal
import commands

def load_module(main, module):
    try:
        md = __import__('modules.mod_' + module, fromlist=[module])
        ma = getattr(md, module)
        return ma(main)
    except ImportError,e:pass
    return None

def setPid(prog):
    fn = '/var/tmp/' + prog + '.pid'
    fpid = open(fn, 'w', 0)
    try:
        fpid.write(str(os.getpid()))
    except IOError:
        raise sys.stderr.write('Error write pid file:' + fn)
    fpid.close()
    
def unsetPid(prog):
    fn = '/var/tmp/' + prog + '.pid'
    if os.path.isfile(fn):
        try:
            print 'rm ', fn
            print commands.getoutput('rm -rf ' + fn)
        except IOError:
            raise sys.stderr.write('Error rm pid file:' + fn)
    
def getPid(prog):
    fn = '/var/tmp/' + prog + '.pid'
    if not os.path.isfile(fn):
        return None
    pid = None
    fpid = open(fn, 'r')
    try:
        pid = fpid.read()
    except IOError:pass
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
    '''控制台，入口程序的基类。 “main”来继承我吧！'''
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
        pass
    
    def _signal_handler(self, signum, frame):
        if __debug__:
            print 'signum:', signum
            print 'frame:', frame
        
        if signum == signal.SIGINT or signum == signal.SIGTERM:
            self._bToClose = True
            print 'To close :', self._bToClose
            
    def isToClose(self):
        return self._bToClose
