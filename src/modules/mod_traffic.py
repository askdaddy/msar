'''
Created on 2013-4-17

@author: seven
'''
from src import argparser, define
import re, time
from output import Output

def S_VALUE(m, n, p):
    d = round(p, 4)
    return (int(n) - int(m)) / d if d != 0 else 0.0 

class traffic_stat(object):
    def __init__(self):
        self.time = time.time()
        self.data = {}
        
    def parse(self, line):
        rex = r'\s*(?P<interface>\w*):\s*(?P<inbytes>\d*)\s*(?P<inpackets>\d*)\s*(?P<inerrs>\d*)\s*(?P<indrop>\d*)\s*(?:\d*\s*){4}(?P<outbytes>\d*)\s*(?P<outpackets>\d*)\s*(?P<outerrs>\d*)\s*(?P<outdrop>\d*)'
        ma = re.match(rex, line, re.IGNORECASE)
        if ma is not None:
            d = ma.groupdict()
            interface = d['interface']
            del d['interface']
            self.data[interface] = d
            
        

class traffic(object):
    def __init__(self, main):
        self.main=main
        main.add_argument('', '--' + self.__class__.__name__, action=argparser.ACTION_SWITCH, help='Net traffic statistics')
    
    def __call__(self):
        # read
        self.pre = self.read_stat()
        time.sleep(.2)
        self.cur = self.read_stat()
        
        ret = {}
        itv = round((self.cur.time - self.pre.time) , 6)
        for interface in self.cur.data:
            v = {}
            v['inbytes'] = "%.2f" % S_VALUE(self.pre.data[interface]['inbytes'], self.cur.data[interface]['inbytes'] , itv)
            v['outbytes'] = "%.2f" % S_VALUE(self.pre.data[interface]['outbytes'], self.cur.data[interface]['outbytes'] , itv)
            ret[interface] = v
        
        self.main.Output.outputData({self.__class__.__name__:ret})

    def read_stat(self):
        stat = traffic_stat()
        f = open(define.NET_DEV, 'r')
        # 
        for line in f:
            ma = re.match(r'\s*.*\:', line, re.IGNORECASE)
            if ma is not None:
                stat.parse(line)
        f.close()

        return stat

