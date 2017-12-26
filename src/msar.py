#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on 2013-4-13

@author: seven
"""

from __future__ import print_function

import argparse
import subprocess
import sys
import time
from straight.plugin import load

import framework
from ICop import ICop
from IPlugin import IPlugin
from framework import Console
from output import Output


class Msar(Console, ICop):
    _args = None

    @property
    def args(self):
        return self._args

    @args.setter
    def args(self, value):
        self._args = value

    def __init__(self):
        Console.__init__(self)
        self.output = Output(self)
        self.cron = 0
        self._run_count = 0
        self.parser = None
        self.plugins = None

        self.init()

    def init(self):
        self.parser = argparse.ArgumentParser(description='Monitor system activity')

        # argument parser
        self.parser.add_argument('-c', '--cron', type=int,
                                 help='Run like Crond')
        self.parser.add_argument('-o', '--output',
                                 help='Output path')
        self.parser.add_argument('-f', '--flow', action='store_true',
                                 help='output appended data')
        self.parser.add_argument('-F', '--force', action='store_true',
                                 help='Kill other pthread and run')
        self.parser.add_argument('-k', '--kill', action='store_true',
                                 help='Kill running msar')
        self.parser.add_argument('-a', '--all', action='store_true',
                                 help='Load all module')

        # Load the plugins
        plugins = load('plugins', subclasses=IPlugin)

        self.plugins = plugins.produce()
        print('{:-^20}'.format(' Loaded plugins '))

        # init plugins
        for p in self.plugins:
            print('{:>20}'.format(p.__class__.__name__))
            p.init(self)

        if len(sys.argv[1:]) == 0:
            self.parser.print_help()
            self.parser.exit()
        self.args = self.parser.parse_args()

    def add_argument(self, *args, **kwargs):
        self.parser.add_argument(*args, **kwargs)

    def out(self, dict_data):
        self.output.outputData(dict_data)

    def run(self):
        # kill itself when received signal
        if self.args.kill:
            self.kill()
            sys.exit(0)

        # Output redirection
        self.output.to(self.args.output)

        # Daemon model
        if self.args.cron:
            if self.args.force:
                self.kill()

            if framework.getPid(self.__class__.__name__) is not None:
                raise Exception('Error: ' + self.__class__.__name__ + ' already run! Pid:' + framework.getPid(
                    self.__class__.__name__))

            framework.daemonize()
            framework.setPid(self.__class__.__name__)
            self.cron = self.args.cron

            if self.cron > 0:  # Ignore the daemon model if cron less than 1
                run_count = 0
                last_run = 0
                while not self.isToClose():
                    if run_count - last_run >= self.cron:
                        self._run_once()
                        last_run = run_count
                    run_count += 1
                    time.sleep(1)
                framework.unsetPid(self.__class__.__name__)

        elif self.args.flow:
            self._run_flow()
        else:
            self._run_once()

    # really run!
    def _run_once(self):
        # Run plugins
        for p in self.plugins:
            p.run()

        self.output.flush()
        self._run_count += 1

    def _run_flow(self):
        while not self.isToClose():
            self._run_once()
            time.sleep(1.0)

    def kill(self):
        pid = framework.getPid(self.__class__.__name__)
        if pid is not None and pid is not '' and int(pid) > 0:
            cmd = 'kill ' + str(pid)
            print(cmd)
            time.sleep(1)
            cmd_out = subprocess.call("rm -rf /var/tmp/msar.*", shell=True)
            print(cmd_out)
            if not framework.getPid(self.__class__.__name__):
                print('OK')
            else:
                print('ERROR')
        else:
            print('no process can be kill!')


if __name__ == '__main__':
    sar = Msar()
    sar.run()
