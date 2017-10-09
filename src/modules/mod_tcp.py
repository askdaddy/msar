# -*- coding: utf-8 -*-
'''
Created on 2013-4-18

@author: seven
'''
from src import argparser, define
import re
import time
from src.modules.mod_io import S_VALUE
from src.output import Output

def S_VALUE(m, n, p):
    d = round(p, 4)
    return (int(n) - int(m)) / d if d != 0 else 0.0  

class tcp_stat(object):
    def __init__(self, line):
        self.time = time.time()
        # Tcp: 
        # RtoAlgorithm 
        # RtoMin 
        # RtoMax 
        # MaxConn 
        # ActiveOpens 
        # PassiveOpens 
        # AttemptFails 
        # EstabResets 
        # CurrEstab 
        # InSegs 
        # OutSegs 
        # RetransSegs 
        # InErrs 
        # OutRsts
        rex = r'^tcp:\s*'
        rex += r'(?P<RtoAlgorithm>\d*)\s*'
        rex += r'(?P<RtoMin>\d*)\s*'
        rex += r'(?P<RtoMax>\d*)\s*'
        rex += r'(?P<MaxConn>-?\d*)\s*'
        rex += r'(?P<ActiveOpens>\d*)\s*'
        rex += r'(?P<PassiveOpens>\d*)\s*'
        rex += r'(?P<AttemptFails>\d*)\s*'
        rex += r'(?P<EstabResets>\d*)\s*'
        rex += r'(?P<CurrEstab>\d*)\s*'
        rex += r'(?P<InSegs>\d*)\s*'
        rex += r'(?P<OutSegs>\d*)\s*'
        rex += r'(?P<RetransSegs>\d*)\s*'
        rex += r'(?P<InErrs>\d*)\s*'
        rex += r'(?P<OutRsts>\d*)\s*'
        ma = re.match(rex, line, re.IGNORECASE)
        if ma is not None:
            self.__dict__.update(ma.groupdict())


class tcp(object):
    def __init__(self, main):
        self.main=main
        main.add_argument('', '--' + self.__class__.__name__, action=argparser.ACTION_SWITCH, help='TCP traffic & connection data')

    def __call__(self):
        self.pre = self.read_tcp()
        time.sleep(.2)
        self.cur = self.read_tcp()
        # st_tcp.ActiveOpens,
#              st_tcp.PassiveOpens,
#              st_tcp.InSegs,
#              st_tcp.OutSegs,
#              st_tcp.RetransSegs
        # 两次探测间隔时间（s）
        self.interval = round((self.cur.time - self.pre.time) , 6)
        ret = {}
        ret['ActiveOpens'] = "%.2f" % S_VALUE(self.pre.ActiveOpens, self.cur.ActiveOpens, self.interval)
        ret['PassiveOpens'] = "%.2f" % S_VALUE(self.pre.PassiveOpens, self.cur.PassiveOpens, self.interval)
        ret['InSegs'] = "%.2f" % S_VALUE(self.pre.InSegs, self.cur.InSegs, self.interval)
        ret['OutSegs'] = "%.2f" % S_VALUE(self.pre.OutSegs, self.cur.OutSegs, self.interval)
        ret['RetransSegs'] = "%.2f" % S_VALUE(self.pre.RetransSegs, self.cur.RetransSegs, self.interval)
        self.main.Output.outputData({self.__class__.__name__:ret})
      
    def read_tcp(self):
        stat = None
        p = open(define.NET_SNMP, 'r')
        for line in p:
            ma = re.match('^tcp:\s*\d+', line, re.IGNORECASE)
            if ma is not None:
                stat = tcp_stat(line)
        p.close()
        return stat
