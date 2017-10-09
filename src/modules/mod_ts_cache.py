# -*- coding: utf-8 -*-
"""
Created on 12-30-2014 11:06

@author: seven
"""
import socket
import struct

from src import argparser
from src.define import TS_MGMTAPISOCK


def fetch_ts_stat(query):
    data = None
    # query from mgmtapisocket
    req = struct.pack('h', 3)  # RECORD_GET
    query_len = len(query)
    req += struct.pack('i', query_len)
    req += query

    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM, 0)
    s.connect(TS_MGMTAPISOCK)
    # print 'Send', repr(req)
    s.sendall(req)
    res = s.recv(1024)
    s.close()
    if res:
        err, = struct.unpack_from('h', res, 0)
        # print err
        if err < 1:
            _, ptr, ptr_l, rec_t = struct.unpack_from('hihh', res, 0)
            # print ptr, ptr_l, rec_t
            if rec_t < 2:
                _, _, _, _, data = struct.unpack_from('hihhi', res, 0)
            elif rec_t == 2:
                _, _, _, _, data_v = struct.unpack_from('hihhf', res, 0)
                data = "%.2f" % (data_v*100)
            elif rec_t == 3:
                _, _, _, _, data_len = struct.unpack_from('hihhh', res, 0)
                data = res[-data_len:]

        # print data
    return data


class ts_cache(object):
    def __init__(self, main):
        self.main = main
        main.add_argument('', '--' + self.__class__.__name__, action=argparser.ACTION_SWITCH,
                          help='trafficserver cache statistics')
        self.records_name = {
            "hit_10s": "proxy.node.cache_hit_ratio_avg_10s",
            "ram_hit_10s": "proxy.node.cache_hit_mem_ratio_avg_10s",
            "bw_hit_10s": "proxy.node.bandwidth_hit_ratio_avg_10s",
            "n_hit": "proxy.process.cache.read.success",
            "n_ram": "proxy.process.cache.ram.read.success",
            "ssd_hit": "proxy.process.cache.ssd.read.success"
        }

    def __call__(self):
        ret = {}
        # read

        for kw, query in self.records_name.items():
            ret[kw] = fetch_ts_stat(query)
        self.main.Output.outputData({self.__class__.__name__: ret})