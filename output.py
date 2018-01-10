# -*- coding: utf-8 -*-
"""
Created on 2013-4-15

@author: seven
"""
from __future__ import print_function

import socket
import sys
import json

# from mysql.connector import Connect
import time


class Output(object):
    def __init__(self, root):
        self._root = root
        self._clear()

    def to(self, url):
        self._url = url

    def outputData(self, data):
        if isinstance(data, dict):
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
            # self._url is a local file
            fs = open(self._url, 'a+')
            sys.stdout = fs
            self.data['timestamp'] = time.time()
            print(json.dumps(self.data), end='\n')
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
                print('{:+{align}{width}}'.format(_k, align='^', width=20))
                self._print_mod(_v)
            else:
                # there is someting wrong!!
                continue

    def _print_mod(self, data):
        for _k, _v in data.items():
            self.print_title_depth += 1
            if isinstance(_v, dict):
                # this is a sub header ,it has sub data
                print('>{:-{align}{width}}'.format(_k, align='<', width=10))
                # print(_k, '>' * 10)
                self._print_mod(_v)
            else:
                print('{}: {}'.format(_k, _v))
