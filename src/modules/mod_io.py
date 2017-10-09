# -*- coding: utf-8 -*-
'''
Created on 2013-4-17

@author: seven
'''
import re, time
import commands
from src import argparser, define
from msar import msar

def S_VALUE(m, n, p):
    d = round(p, 6)
    return (int(n) - int(m)) / d if d != 0 else 0.0  # *1024

class record(object):
    def parse(self, pre_stat = None, cur_stat = None):
# https://www.kernel.org/doc/Documentation/iostats.txt
# Field  1 -- # of reads completed
#    This is the total number of reads completed successfully.
# Field  2 -- # of reads merged, field 6 -- # of writes merged
#    Reads and writes which are adjacent to each other may be merged for
#    efficiency.  Thus two 4K reads may become one 8K read before it is
#    ultimately handed to the disk, and so it will be counted (and queued)
#    as only one I/O.  This field lets you know how often this was done.
# Field  3 -- # of sectors read
#    This is the total number of sectors read successfully.
# Field  4 -- # of milliseconds spent reading
#    This is the total number of milliseconds spent by all reads (as
#    measured from __make_request() to end_that_request_last()).
# Field  5 -- # of writes completed
#    This is the total number of writes completed successfully.
# Field  7 -- # of sectors written
#    This is the total number of sectors written successfully.
# Field  8 -- # of milliseconds spent writing
#    This is the total number of milliseconds spent by all writes (as
#    measured from __make_request() to end_that_request_last()).
# Field  9 -- # of I/Os currently in progress
#    The only field that should go to zero. Incremented as requests are
#    given to appropriate struct request_queue and decremented as they finish.
# Field 10 -- # of milliseconds spent doing I/Os
#    This field increases so long as field 9 is nonzero.
# Field 11 -- weighted # of milliseconds spent doing I/Os
#    This field is incremented at each I/O start, I/O completion, I/O
#    merge, or read of these stats by the number of I/Os in progress
#    (field 9) times the number of milliseconds spent doing I/O since the
#    last update of this field.  This can provide an easy measure of both
#    I/O completion time and the backlog that may be accumulating.
####################################################################################
#        第1列 : major - 磁盘主设备号
#        第2列 : minor - 磁盘次设备号
#        第3列 : name - 磁盘的设备名
#
#        第4列 : rio - 读请求总数
#        第5列 : rmerge - 合并的读请求总数
#        第6列 : rsect - 读扇区总数
#        第7列 : rtick - 读数据花费的时间，单位是ms.(从__make_request到 end_that_request_last)
#        第8列 : wio - 写请求总数
#        第9列 : wmerge - 合并的写请求总数
#        第10列 :wsect - 写扇区总数
#        第11列 :wtick - 写数据花费的时间，单位是ms. (从__make_request到 end_that_request_last)
#        第12列 :iopgr - 现在正在进行的I/O数,等于I/O队列中请求数
#        第13列 :ticks - 系统真正花费在I/O上的时间，除去重复等待时间
#        第14列 :rqtick - 系统在I/O上花费的时间
        rex = r'\s*'
        rex += r'(?P<major>\d*)\s*'     
        rex += r'(?P<minor>\d*)\s*'     
        rex += r'(?P<name>\S*)\s*'
              
        rex += r'(?P<rio>\d*)\s*'  # 1
        rex += r'(?P<rmerge>\d*)\s*'  # 2
        rex += r'(?P<rsect>\d*)\s*'  # 3
        rex += r'(?P<rtick>\d*)\s*'  # 4
        rex += r'(?P<wio>\d*)\s*'  # 5
        rex += r'(?P<wmerge>\d*)\s*'  # 6
        rex += r'(?P<wsect>\d*)\s*'  # 7
        rex += r'(?P<wtick>\d*)\s*'  # 8
        rex += r'(?P<iopgr>\d*)\s*'  # 9
        rex += r'(?P<ticks>\d*)\s*'  # 10
        rex += r'(?P<rqtick>\d*)\s*'  # 11
        
        p = re.compile(rex, re.IGNORECASE)
        if pre_stat is not None:
            self.pre_time = round(time.time(), 6)
            res = p.match(pre_stat)
            if res is not None:
                self.pre = res.groupdict()
        if cur_stat is not None:
            self.cur_time = round(time.time(), 6)
            res = p.match(cur_stat)
            if res is not None:
                self.cur = res.groupdict()
    def calc(self):
        # 两次探测间隔时间（s）
        self.interval = round((self.cur_time - self.pre_time) , 6)
        # st_array[0] = rd_merges / (inter * 1.0);rrqms
        # st_array[1] = wr_merges / (inter * 1.0);wrqms
        # st_array[2] = rd_ios / (inter * 1.0);rs
        # st_array[3] = wr_ios / (inter * 1.0);ws
        # st_array[4] = rd_sectors / (inter * 2.0);rsecs
        # st_array[5] = wr_sectors / (inter * 2.0);wsecs
        # st_array[6] = n_ios ? n_kbytes / n_ios : 0.0;rqsize
        # st_array[7] = aveq / (inter * 1000);qusize
        # st_array[8] = n_ios ? n_ticks / n_ios : 0.0;await
        # st_array[9] = n_ios ? ticks / n_ios : 0.0;svctm
        # st_array[10] = ticks / (inter * 10.0); /* percentage! */util
        ret = {}
        # -- helpers
        # io读操作数量
        rd_io = int(self.cur['rio']) - int(self.pre['rio'])
        # 读操作耗时ms
        rd_tick = int(self.cur['rtick']) - int(self.pre['rtick'])
        # 读取扇区总数
        rd_sect = int(self.cur['rsect']) - int(self.pre['rsect'])
        # io写操作数量
        wr_io = int(self.cur['wio']) - int(self.pre['wio'])
        # 写操作耗时ms
        wr_tick = int(self.cur['wtick']) - int(self.pre['wtick'])
        # 写入扇区总数
        wr_sect = int(self.cur['wsect']) - int(self.pre['wsect'])
        # 总io操作数量
        n_io = rd_io + wr_io
        # helpers --
        
        ret['name'] = self.pre['name']
        # rrqm/s:     每秒进行 merge 的读操作数目。
        ret['rrqms'] = "%.2f" % S_VALUE(self.pre['rmerge'], self.cur['rmerge'], self.interval)
        # wrqm/s:     每秒进行 merge 的写操作数目。
        ret['wrqms'] = "%.2f" % S_VALUE(self.pre['wmerge'], self.cur['wmerge'], self.interval)
        # r/s:       每秒完成的读 I/O 设备次数。即 rio/s
        ret['rs'] = "%.2f" % S_VALUE(self.pre['rio'], self.cur['rio'], self.interval)
        # w/s:       每秒完成的写 I/O 设备次数。即 wio/s
        ret['ws'] = "%.2f" % S_VALUE(self.pre['wio'], self.cur['wio'], self.interval)
        # rsec/s:     每秒读扇区数。即 rsect/s
        ret['rsecs'] = "%.2f" % S_VALUE(self.pre['rsect'], self.cur['rsect'], self.interval)
        # wsec/s:     每秒写扇区数。即 wsect/s
        ret['wsecs'] = "%.2f" % S_VALUE(self.pre['wsect'], self.cur['wsect'], self.interval)
        # rkB/s:     每秒读K字节数。是 rsect/s 的一半，因为每扇区大小为512字节。
        ret['rkBs'] = "%.2f" % (S_VALUE(self.pre['rsect'], self.cur['rsect'], self.interval) / 2.0)
        # wkB/s:     每秒写K字节数。是 wsect/s 的一半。
        ret['wkBs'] = "%.2f" % (S_VALUE(self.pre['wsect'], self.cur['wsect'], self.interval) / 2.0)
        
        # avgrq-sz:   平均每次设备I/O操作的数据大小 (扇区)。即 (rsect+wsect)/(rio+wio)
        ret['avgrq-sz'] = "%.2f" % ((rd_sect + wr_sect) / (n_io * 1.0) if n_io != 0 else 0)
        # avgqu-sz:   平均I/O队列长度。即 aveq/1000 (因为aveq的单位为毫秒)。
        ret['avgqu-sz'] = "%.2f" % (S_VALUE(self.pre['rqtick'], self.cur['rqtick'], self.interval) / 1000.0)
        # 平均每次设备读I/O操作的等待时间 (毫秒)
        ret['r_await'] = "%.2f" % (rd_tick / (rd_io * 1.0) if rd_io != 0 else 0.0)
        # 平均每次设备读I/O操作的等待时间 (毫秒)
        ret['w_await'] = "%.2f" % (wr_tick / (wr_io * 1.0) if wr_io != 0 else 0.0)
        # 平均每次设备I/O操作的等待时间 (毫秒).即 delta(ruse+wuse)/delta(rio+wio)
        ret['await'] = "%.2f" % ((rd_tick + wr_tick) / (n_io * 1.0) if n_io != 0 else 0.0)
        
        tput = ((int(self.cur['rio']) + int(self.pre['wio'])) - (int(self.pre['rio']) + int(self.pre['wio'])))
        # svctm:     平均每次设备I/O操作的服务时间 (毫秒)。即 use/(rio+wio)
        ret['svctm'] = "%.2f" % ((int(self.cur['ticks']) - int(self.pre['ticks'])) / (tput * 1.0) if tput != 0 else 0.0)
        
        uses = S_VALUE(self.pre['ticks'], self.cur['ticks'], self.interval)
        # %util:     一秒中有百分之多少的时间用于 I/O 操作，或者说一秒中有多少时间I/O队列是非空的,即use/1000 (因为use的单位为毫秒),如果 %util 接近 100%，说明产生的I/O请求太多，I/O系统已经满负荷，该磁盘可能存在瓶颈。
        ret['util'] = "%.2f" % (uses / 10.0)
        
        return ret
        
        
class io(object):
    def __init__(self, main):
        self.main = main
        main.add_argument('', '--' + self.__class__.__name__, action = argparser.ACTION_SWITCH, help = 'Linux I/O performance')
        self.partitions = None
        self.records = {}
        
    def __call__(self):
        records = []
            
        # p = open(define.DISKSTATS, 'r', 0)
        presult = commands.getoutput("cat /proc/diskstats")
        # with open(r'/tmp/ptmp.txt','w') as f:
        #    f.write(presult)
        # p = open(r'/tmp/ptmp.txt','r',0)
        p = presult.strip().split('\n')
        for line in p:
            r = record()
            r.parse(pre_stat = line)
            records.append(r)
        # p.close()
        
        time.sleep(.2)
        
        # c = open(define.DISKSTATS, 'r', 0)
        cresult = commands.getoutput("cat /proc/diskstats")
        # with open(r'/tmp/ctmp.txt', 'w') as f:
        #    f.write(cresult)
        # c = open(r'/tmp/ctmp.txt', 'r', 0)
        c = cresult.strip().split('\n')
        i = 0
        for line in c:
            r = records[i]
            r.parse(cur_stat = line)
            self.set_record(r.calc())
            i += 1
        # c.close()
        
        self.main.Output.outputData({self.__class__.__name__:self.records})
        
        
    def set_record(self, records):
        name = records['name']
        del records['name']
        if self.inPartitions(name):
            self.records[name] = records
            
    def inPartitions(self, name):
        p = re.compile('^\w*\d+', re.IGNORECASE)
        m = p.match(name)
        if m is not None:
            return False
        
        if self.partitions is None:
            f = open(define.PARTITIONS, 'r')
            self.partitions = f.read()
            f.close()
            
        if name in self.partitions:
            return True
        return False
