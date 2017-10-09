#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Created on 2013-4-13

@author: seven
'''
import sys
import os


def AddPyPath(new_path):
    if not os.path.exists(new_path): return False

    new_path = os.path.abspath(new_path)

    for p in sys.path:
        p = os.path.abspath(p)
        if new_path in (p, p + os.sep):
            return True
    sys.path.append(new_path)


AddPyPath(os.path.split(os.path.realpath(__file__))[0][0:os.path.split(os.path.realpath(__file__))[0].rfind('/')])
AddPyPath(os.path.split(os.path.realpath(__file__))[0])

import time
import commands
import re
from output import Output
from framework import Console
import argparser
import framework


class msar(Console):
    def __init__(self):
        self.Output = Output(self)
        Console.__init__(self)
        self.mod_path = os.path.split(os.path.realpath(__file__))[0] + '/modules'
        self.cron = 0
        self.list_modules()
        self.parser_arguments()

        self._run_count = 0


    def parser_arguments(self):
        self.parser = argparser.argparser()

        for mod in self.available_modules:
            framework.load_module(self, mod)

        self.parser.add_argument('-c', '--cron', action=argparser.ACTION_OPTIONAL, help='Run as Crond')
        self.parser.add_argument('-o', '--output', action=argparser.ACTION_OPTIONAL, help='Output path')
        self.parser.add_argument('-f', '--fllow', action=argparser.ACTION_SWITCH, help='output appended data')

        self.parser.add_argument('-F', '--force', action=argparser.ACTION_SWITCH, help='Kill other pthread and run')
        self.parser.add_argument('-k', '--kill', action=argparser.ACTION_SWITCH, help='Kill running msar')
        self.parser.add_argument('-a', '--all', action=argparser.ACTION_SWITCH, help='Load all module')
        self.parser.parse_argument(sys.argv[1:])

    def add_argument(self, *args, **kwargs):
        self.parser.add_argument(*args, **kwargs)

    def list_modules(self):
        self.available_modules = []
        p = re.compile(r'^mod_(?P<mod>\w*)\.py$', re.IGNORECASE)
        for root, dirs, files in os.walk(self.mod_path):
            for fn in files:
                ma = p.match(fn)
                if ma is not None:
                    self.available_modules.append(ma.groupdict()['mod'])
        self.available_modules = {}.fromkeys(self.available_modules).keys()

    def reload_modules(self):
        self.modules = []

        if self.parser.get_argument('all'):
            for mod in self.available_modules:
                module = framework.load_module(self, mod)
                if module is not None:
                    self.modules.append(module)
            return

        for arg in self.parser:
            if arg.value:
                module = framework.load_module(self, arg.name())
                if module is not None:
                    self.modules.append(module)

    def run_modules(self):
        for module in self.modules:
            if module is not None:
                module()

    def shutdown_modules(self):
        del self.modules

    def run(self):
        # 如果收到kill参数就开始自杀
        if self.parser.get_argument('kill'):
            self.kill()
            sys.exit(0)
        # 载入所有需要运行的模块
        self.reload_modules()

        # 输出重定向
        msar.Output.to(self.parser.get_argument('output'))
        # 守护进程模式
        if self.parser.get_argument('cron') is not None:
            if self.parser.get_argument('force'):
                self.kill()

            if framework.getPid(self.__class__.__name__) is not None:
                raise Exception('Error: ' + self.__class__.__name__ + ' already run! Pid:' + framework.getPid(
                    self.__class__.__name__))

            framework.daemonize()
            framework.setPid(self.__class__.__name__)
            self.cron = int(self.parser.get_argument('cron'))

            if self.cron > 0:  # 如果小于等于0没有必要运行守护
                run_count = 0
                last_run = 0
                while not self.isToClose():
                    if run_count - last_run >= self.cron:
                        self._run_once()
                        last_run = run_count
                    run_count += 1
                    time.sleep(1)
                framework.unsetPid(self.__class__.__name__)
        elif self.parser.get_argument('fllow'):
            self._run_fllow()
        else:
            self._run_once()

        self.shutdown_modules()
        pass

    # really run!
    def _run_once(self):
        self.run_modules()
        msar.Output.flush()
        self._run_count += 1

    def _run_fllow(self):
        while not self.isToClose():
            self._run_once()
            time.sleep(1.0)

    def kill(self):
        pid = framework.getPid(self.__class__.__name__)
        if pid is not None and pid is not '' and int(pid) > 0:
            cmd = 'kill ' + str(pid)
            print cmd
            print commands.getoutput(cmd)
            time.sleep(1)
            print commands.getoutput('rm -rf /var/tmp/msar.*')
            if not framework.getPid(self.__class__.__name__):
                print 'OK'
            else:
                print 'ERROR'
        else:
            print 'no process can be kill!'


if __name__ == '__main__':
    msar = msar()
    msar.run()    
    
        
    
