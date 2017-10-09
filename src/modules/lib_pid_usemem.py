# -*- coding: utf-8 -*-
'''
Created on 2013-4-23

@author: xie
'''

import re

class PidUserMem(object):
    '''
    根据进程号，统计当前进程使用的物理内存大小
    '''
    def __init__(self, pid):
        self.PID_STATUS = "/proc/" + str(pid) + "/status"
        
        
    def getPidUserMem(self):
        ret = {}
        f = open(self.PID_STATUS, 'r')
        p = re.compile(r'\w*:.*\n\w*:.*\n\w*:.*\n\w*:.*\n\w*:.*\n\w*:.*\n\w*:.*\n\w*:.*\n\w*:.*\n\w*:.*\n\w*:.*\n\w*:.*\n\w*:.*\n\w*:.*\n\w*:.*\n\w*:\s*(?P<kvmrss>\d*).*\n', re.IGNORECASE)
        res = p.match(f.read())
        if res is not None:
            ret = res.groupdict()
        f.close()    
        return ret['kvmrss']  # 单位KB
        
