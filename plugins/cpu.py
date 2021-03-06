"""
Created on 2013-4-13

@author: seven
"""
import re
import time

import define
from IPlugin import IPlugin


class Cpu(IPlugin):
    cop = None

    def constructor(self, cop):
        # print ('{}.init'.format(self.__class__.__name__))
        self.cop = cop
        cop.add_argument('--cpu', action='store_true',
                         help='CPU share (user, system, interrupt, nice, & idle)')

    @property
    def stat(self):
        f = open(define.STAT, 'r')
        ret = {}
        p = re.compile(
            r'(?P<cpu>cpu\d*)\s*(?P<us>\d*)\s*(?P<ni>\d*)\s*(?P<sy>\d*)\s*(?P<id>\d*)\s*(?P<wa>\d*)\s*(?P<hi>\d*)\s*(?P<si>\d*)\s*(?P<st>\d*)\s*(?P<gu>\d*)',
            re.IGNORECASE)
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

    def run(self):
        if self.cop.args.cpu is not True and self.cop.args.all is not True:
            return

        ret = {}
        pre_cpu = self.stat
        time.sleep(0.05)
        cur_cpu = self.stat

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
        self.cop.out({self.__class__.__name__: ret})
