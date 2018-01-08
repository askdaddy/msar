"""
Created on 2013-4-16

@author: seven
"""

import re

import define
from IPlugin import IPlugin


class Load(IPlugin):
    def constructor(self, cop):
        self.cop = cop
        cop.add_argument('--load' , action='store_true',
                          help='System Run Queue and load average')

    def run(self):
        if self.cop.args.load is not True and self.cop.args.all is not True:
            return
        ret = {}
        f = open(define.LOADAVG, 'r')
        p = re.compile(r'^(?P<load1>\d*\.?\d*)\s(?P<load5>\d*\.?\d*)\s(?P<load15>\d*\.?\d*)\s', re.IGNORECASE)

        ma = p.match(f.read())
        if ma is not None:
            ret = ma.groupdict()
        f.close()
        self.cop.out({self.__class__.__name__: ret})
