'''
Created on 2013-4-22

@author: seven
'''
from src import argparser, define
import commands, re
import httplib
from output import Output
from modules.lib_pid_usemem import PidUserMem

def S_VALUE(m, n, p):
    d = round(p, 4)
    print "-", (int(n) - int(m))
    print "d", d 
    return (int(n) - int(m)) / d if d != 0 else 0.0 
def SP_VALUE(p):
    return round(float(p) * 100, 4)

class squid_info(object):
    def __init__(self):
        self.cur = None
        self.info = None
        
    def parse(self, usemem, info):
        self.cur = self._parse(usemem, info)
            
    def _parse(self, usemem, info):
        self.info = {}
        rexes = []
        rexes.append(r'.*Start\sTime:\s*(?P<start>.*)')
        rexes.append(r'.*HTTP\srequests\sreceived:\s*(?P<requests>\d*)')
        rexes.append(r'\s*HTTP\sRequests.*:\s*(?P<avg_requests5>\d*\.\d*)\s*(?P<avg_requests60>\d*\.\d*)')
        
        rexes.append(r'\s*Cache\sMisses:\s*(?P<avg_miss5>\d*\.\d*)\s*(?P<avg_miss60>\d*\.\d*)')
        rexes.append(r'\s*Cache\sHits:\s*(?P<avg_hits5>\d*\.\d*)\s*(?P<avg_hits60>\d*\.\d*)')
        rexes.append(r'\s*Near\sHits:\s*(?P<avg_near_hits5>\d*\.\d*)\s*(?P<avg_near_hits60>\d*\.\d*)')
        rexes.append(r'\s*Not-Modified\sReplies:\s*(?P<avg_not_mod5>\d*\.\d*)\s*(?P<avg_not_mod60>\d*\.\d*)')
        
        rexes.append(r'.*UP\sTime:\s*(?P<up>\d*\.\d*)\s')
        rexes.append(r'.*CPU\sUsage:\s*(?P<cpu>\d*\.\d*)%?')
        
#        rexes.append(r'.*Total\sin\suse:\s*(?P<kmem_in_use>\d*)\s*')
#        rexes.append(r'.*Total\sfree:\s*(?P<kmem_free>\d*)\s*')
        # Internal Data Structures
        rexes.append(r'\s*(?P<store_obj>\d*)\sStoreEntries\s*$')
        rexes.append(r'\s*(?P<mem_obj>\d*)\s*StoreEntries\s*with\s*MemObjects')
        rexes.append(r'\s*(?P<hot_obj>\d*)\s*Hot\s*Object\s*Cache\s*Items')
        rexes.append(r'\s*(?P<disc_obj>\d*)\s*on-disk\s*objects')
        for line in info.split('\n'):
            for rex in rexes:
                ma = re.match(rex, line, re.IGNORECASE)
                if ma is not None:
                    self.info.update(ma.groupdict())
        self.info['cpu'] = '%.2f' % SP_VALUE(self.info['cpu']) 
        self.info['avg_requests5'] = '%.2f' % SP_VALUE(self.info['avg_requests5']) 
        self.info['avg_requests60'] = '%.2f' % SP_VALUE(self.info['avg_requests60'])
        self.info['avg_miss5'] = '%.2f' % SP_VALUE(self.info['avg_miss5'])
        self.info['avg_miss60'] = '%.2f' % SP_VALUE(self.info['avg_miss60'])
        self.info['avg_not_mod5'] = '%.2f' % SP_VALUE(self.info['avg_not_mod5'])
        self.info['avg_not_mod60'] = '%.2f' % SP_VALUE(self.info['avg_not_mod60'])
        
        self.info['avg_hits5'] = '%.2f' % SP_VALUE(self.info['avg_hits5'])
        self.info['avg_hits60'] = '%.2f' % SP_VALUE(self.info['avg_hits60'])
        
        self.info['avg_near_hits5'] = '%.2f' % SP_VALUE(self.info['avg_near_hits5'])
        self.info['avg_near_hits60'] = '%.2f' % SP_VALUE(self.info['avg_near_hits60'])  
        self.info['ktotal_mem'] = self._getTotalMem()
        self.info['kmem_in_use'] = "%.2f" % SP_VALUE(float(usemem) / (float(self.info['ktotal_mem']) * 1.0))
                 
    def getInfo(self):
        return self.info
    
    # total mem
    def _getTotalMem(self):
        ret = {}
        f = open(define.MEMINFO, 'r')
        p = re.compile(r'\w*:\s*(?P<total>\d*).*\n', re.IGNORECASE)
        res = p.match(f.read())
        if res is not None:
            ret = res.groupdict()
        return ret['total'];  

class squid(object):
    def __init__(self, main):
        self.main=main
        main.add_argument('', '--' + self.__class__.__name__, action=argparser.ACTION_SWITCH, help='Squid info')
        self.squids = {}
        
    def __call__(self):
        ret = {}
        ports = self.getPort()
            
        for k, p in ports.items():
            self.squids[p] = squid_info()
            self.readInfo(k, p)
            ret[p] = self.squids[p].getInfo()
        
        self.main.Output.outputData({self.__class__.__name__:ret})
    
    def readInfo(self, pid, port):
        info = self.squids[port]
        if info is None:
            return
        headers = {"Accept":"*/*",
                   "Host":"localhost"};  
        conn = httplib.HTTPConnection('localhost', port=port);
        conn.request(method="GET", url='cache_object://localhost/info', headers=headers);
        response = conn.getresponse()
        
        usemem = self._readPidMem(pid)
        
        
        if response.status == 200:
            info.parse(usemem, response.read())
            
    def _readPidMem(self, pid):
        if pid is None:
            return 0
        pidUserMem = PidUserMem(pid)
        return pidUserMem.getPidUserMem()
        
    def getPort(self):
        ports = {}
        f = commands.getoutput('netstat -lpn').split('\n')
        rex = r'.*:(?P<port>\d*)\s*.*:.*LISTEN\s*(?P<pid>\d*)/.?squid.?'
        for line in f:
            ma = re.match(rex, line, re.IGNORECASE)
            if ma is not None and ma.group('port') is not None:
                pid = ma.group('pid')
                ports[pid] = ma.group('port')
#                ports.append(ma.group('port'))
        return ports
