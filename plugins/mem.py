"""
Created on 2013-4-16

@author: seven
"""
import re

import define
from IPlugin import IPlugin


class Stats(object):
    def __init__(self):
        self.total = 0
        self.free = 0
        self.buffers = 0
        self.cached = 0
        self.act = 0
        self.inact = 0


class Mem(IPlugin):
    def constructor(self, cop):
        self.cop = cop
        cop.add_argument('--mem', action='store_true', help='Physical memory share in Kb')

    def run(self):
        if self.cop.args.mem is not True and self.cop.args.all is not True:
            return

        stats = Stats()

        f = open(define.MEMINFO, 'r')
        p = re.compile(
            r'\w*:\s*(\d*).*',
            re.IGNORECASE
        )

        for line in f:
            if 'MemTotal' in line:
                res = p.match(line)
                if res is not None:
                    stats.total = res.group(1)
            elif 'MemFree' in line:
                res = p.match(line)
                if res is not None:
                    stats.free = res.group(1)
            elif 'Buffers' in line:
                res = p.match(line)
                if res is not None:
                    stats.buffers = res.group(1)
            elif 'Cached' in line:
                res = p.match(line)
                if res is not None:
                    stats.cached = res.group(1)
            elif 'Active' in line:
                res = p.match(line)
                if res is not None:
                    stats.act = res.group(1)
            elif 'Inactive' in line:
                res = p.match(line)
                if res is not None:
                    stats.inact = res.group(1)

        f.close()

        self.cop.out({self.__class__.__name__: stats.__dict__})
