# -*- coding: utf-8 -*-
'''
Created on 2013-4-19

@author: sxie
'''
from src import argparser, define
import re
import time
from src.modules.mod_io import S_VALUE
from output import Output
from msar.src.msar import msar

def S_VALUE(m, n, p):
    d = round(p, 4)
    return (int(n) - int(m)) / d if d != 0 else 0.0  

class udp_stat(object):
    def __init__(self, line):
        self.time = time.time()
        # Udp: 
        # InDatagrams 
        # NoPorts 
        # InErrors 
        # OutDatagrams 
        # RcvbufErrors 
        # SndbufErrors
        rex = r'^udp:\s*'
        rex += r'(?P<InDatagrams>\d*)\s*'
        rex += r'(?P<NoPorts>\d*)\s*'
        rex += r'(?P<InErrors>\d*)\s*'
        rex += r'(?P<OutDatagrams>-?\d*)\s*'
        rex += r'(?P<RcvbufErrors>\d*)\s*'
        rex += r'(?P<SndbufErrors>\d*)\s*'
        ma = re.match(rex, line, re.IGNORECASE)
        if ma is not None:
            self.__dict__.update(ma.groupdict())


class udp(object):
    def __init__(self, main):
        self.main=main
        main.add_argument('', '--' + self.__class__.__name__, action=argparser.ACTION_SWITCH, help='udp traffic & connection data')

    def __call__(self):
        self.pre = self.read_udp()
        time.sleep(.2)
        self.cur = self.read_udp()

        # 两次探测间隔时间（s）
        self.interval = round((self.cur.time - self.pre.time) , 6)
        
        ret = {}
        ret['InDatagrams'] = "%.2f" % S_VALUE(self.pre.InDatagrams, self.cur.InDatagrams, self.interval)
        ret['OutDatagrams'] = "%.2f" % S_VALUE(self.pre.OutDatagrams, self.cur.OutDatagrams, self.interval)
        ret['NoPorts'] = "%.2f" % S_VALUE(self.pre.NoPorts, self.cur.NoPorts, self.interval)
        ret['InErrors'] = "%.2f" % S_VALUE(self.pre.InErrors, self.cur.InErrors, self.interval)
        self.main.Output.outputData({self.__class__.__name__:ret})
      
    def read_udp(self):
        stat = None
        p = open(define.NET_SNMP, 'r')
        for line in p:
            ma = re.match('^udp:\s*\d+', line, re.IGNORECASE)
            if ma is not None:
                stat = udp_stat(line)
        p.close()
        return stat

