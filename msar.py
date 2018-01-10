#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Created on 2013-4-13

@author: seven
"""

from __future__ import print_function

import argparse
import sys
import time
from straight.plugin import load

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
        self.parser.add_argument('-o', '--output',
                                 help='Output path')
        self.parser.add_argument('-n', '--interval', nargs='?', const=1, type=int,
                                 help='Seconds to wait between updates')
        self.parser.add_argument('-a', '--all', action='store_true',
                                 help='Load all module')

        # Load the plugins
        plugins = load('plugins', subclasses=IPlugin)

        self.plugins = plugins.produce()
        # print('{:-^20}'.format(' Loaded plugins '))

        # init plugins
        for p in self.plugins:
            # print('{:>20}'.format(p.__class__.__name__))
            p.constructor(self)

        if len(sys.argv[1:]) == 0:
            self.parser.print_help()
            self.parser.exit()
        self.args = self.parser.parse_args()

    def add_argument(self, *args, **kwargs):
        self.parser.add_argument(*args, **kwargs)

    def out(self, dict_data):
        self.output.outputData(dict_data)

    def run(self):
        # Output redirection
        self.output.to(self.args.output)

        if self.args.interval:
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
            # print('{}/Every {}s\t Run {} times.'.format(time.strftime("%a %b %d %H:%M:%S", time.localtime()),
            #                                             self.args.interval, self._run_count))
            self._run_once()
            time.sleep(1.0 * self.args.interval)


if __name__ == '__main__':
    Msar().run()
