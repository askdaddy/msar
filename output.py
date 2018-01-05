# -*- coding: utf-8 -*-
"""
Created on 2013-4-15

@author: seven
"""
from __future__ import print_function

import socket
import sys
import types


# from mysql.connector import Connect

class Output(object):
    def __init__(self, root):
        self._root = root
        self._clear()

    def to(self, url):
        self._url = url

    def outputData(self, data):
        if type(data) is types.DictType:
            self.data.update(data)
            return

    def _clear(self):
        self.data = {}
        self.data['hostname'] = socket.gethostname()

    def flush(self, *args, **kwds):
        if self._IsUrl() is True:
            self._postData()
        else:
            self._writeLocal()

        self._clear()

    # 判断是否是URL
    def _IsUrl(self):
        if self._url is None:
            return False

        if self._url.find('http://') is 0:
            return True
        return False

    def _postData(self):
        # TODO post data to http
        pass

    # 将数据写入本地
    def _writeLocal(self):
        if self._url is None:
            # self._url = '/dev/null'
            self._print()
            return
        saveout = sys.stdout
        fs = None
        try:
            fs = open(self._url, 'w+')
            sys.stdout = fs
            print (self.data)
        except:
            pass
        sys.stdout = saveout

    def _print(self):
        # 解析所有模块,打印表头
        for _k, _v in self.data.items():
            if _k == 'hostname':
                continue
            # we are in top level
            self.print_title_depth = 0
            if isinstance(_v, dict):
                print ('{:+{align}{width}}'.format(_k, align='^', width=20 + len(_k)))
                self._print_mod(_v)
            else:
                # there is someting wrong!!
                continue
            print ('')

    def _print_mod(self, data):
        for _k, _v in data.items():
            self.print_title_depth += 1
            if isinstance(_v, dict):
                print (_k, '>' * 10)
                self._print_mod(_v)
            else:
                print (_k, ':', _v, '\t')
        print ('')
