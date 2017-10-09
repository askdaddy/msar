'''
Created on 2013-4-13

@author: seven
'''
import re
import time
from src import argparser, define
from src.msar import msar
  
class cpu(object):
    def __init__(self, main):
        self.main = main
        main.add_argument('', '--cpu', action = argparser.ACTION_SWITCH, help = 'CPU share (user, system, interrupt, nice, & idle)')
        
    def __call__(self):
        self.setStat()

    def readStat(self):
        f = open(define.STAT, 'r')
        ret = {}
        p = re.compile(r'(?P<cpu>cpu\d*)\s*(?P<us>\d*)\s*(?P<ni>\d*)\s*(?P<sy>\d*)\s*(?P<id>\d*)\s*(?P<wa>\d*)\s*(?P<hi>\d*)\s*(?P<si>\d*)\s*(?P<st>\d*)\s*(?P<gu>\d*)', re.IGNORECASE)
        for line in f:
            res = p.match(line)
            if res is not None:
                d = res.groupdict()
                cpuno = d['cpu'][3:]
                if cpuno == '':
                    d['cpuno'] = ''
                else:
                    d['cpuno'] = '%02d' % int(cpuno)
                ret[d['cpu']] = d
        f.close()
        return ret

    def setStat(self):
        ret = {}
        pre_cpu = self.readStat()
        time.sleep(0.05)
        cur_cpu = self.readStat()
        
        for k in cur_cpu.keys():
            pre = pre_cpu[k]
            cur = cur_cpu[k]
            
            user = int(cur['us']) - int(pre['us'])
            nice = int(cur['ni']) - int(pre['ni'])
            system = int(cur['sy']) - int(pre['sy'])
            idle = int(cur['id']) - int(pre['id'])
            iowait = int(cur['wa']) - int(pre['wa'])
            irq = int(cur['hi']) - int(pre['hi'])
            softirq = int(cur['si']) - int(pre['si'])
            steal = int(cur['st']) - int(pre['st'])
            guest = int(cur['gu']) - int(pre['gu'])
            
            total = user + nice + system + idle + iowait + irq + softirq + steal + guest
            data = {}
            data['us'] = "%.1f" % (user / (total * 1.0) * 100)
            data['sy'] = "%.1f" % (system / (total * 1.0) * 100)
            data['id'] = "%.1f" % (idle / (total * 1.0) * 100)
            data['wa'] = "%.1f" % (iowait / (total * 1.0) * 100)
            ret['cpu' + cur['cpuno']] = data
        self.main.Output.outputData({self.__class__.__name__:ret})
        
