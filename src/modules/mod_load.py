'''
Created on 2013-4-16

@author: seven
'''
import re
from src import argparser, define
from src.output import Output

class load(object):
    def __init__(self, main):
        self.main=main
        main.add_argument('', '--' + self.__class__.__name__, action=argparser.ACTION_SWITCH, help='System Run Queue and load average')
    def __call__(self):
        ret = {}
        f = open(define.LOADAVG, 'r')
        p = re.compile(r'^(?P<one>\d*\.?\d*)\s(?P<five>\d*\.?\d*)\s(?P<fifteen>\d*\.?\d*)\s', re.IGNORECASE)
        
        ma = p.match(f.read())
        if ma is not None:
            ret = ma.groupdict()
        f.close()
        self.main.Output.outputData({self.__class__.__name__:ret})
        
