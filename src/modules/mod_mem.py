'''
Created on 2013-4-16

@author: seven
'''
from src import argparser, define
import re
from output import Output

class mem(object):
    def __init__(self, main):
        self.main = main
        main.add_argument('', '--mem', action = argparser.ACTION_SWITCH, help = 'Collect Mem usage')
        
    def __call__(self):
        ret = {}
        f = open(define.MEMINFO, 'r')
        p = re.compile(r'\w*:\s*(?P<total>\d*).*\n\w*:\s*(?P<free>\d*).*\n\w*:\s*(?P<buffer>\d*).*\n\w*:\s*(?P<cache>\d*).*\n', re.IGNORECASE)
        res = p.match(f.read())
        if res is not None:
            ret = res.groupdict()
        f.close()    
        data = {}
        data['total'] = ret['total']
        data['useper'] = "%.1f" % ((float(data['total']) - (float(ret['free']) + float(ret['buffer']) + float(ret['cache']))) / (float(data['total']) * 1.0) * 100) 
        self.main.Output.outputData({self.__class__.__name__:data})
        
