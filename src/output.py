# -*- coding: utf-8 -*-
'''
Created on 2013-4-15

@author: seven
'''

import sys
import httplib
import urllib
import types
import urlparse
import socket
import time
import json
import traceback

# from mysql.connector import Connect

class Output(object):
    def __init__(self, root):
        self._resetData()
        self._root = root

    def to(self, url):
        self._url = url

    def outputData(self, data):
        if type(data) is types.DictType:
            self.data.update(data)
            return

    def _resetData(self):
        self.data = {}
        self.data['hostname'] = socket.gethostname()

    def flush(self, *args, **kwds):
        if self._IsUrl() is True:
            self._postData()
        else:

            self._writeLocal()
        self._resetData()

    # 判断是否是URL
    def _IsUrl(self):
        if self._url is None:
            return False

        if self._url.find('http://') is 0:
            return True
        return False

    # 带URL 的 POST
    def _postData(self):
        # 定义需要进行发送的数据 
        self.data['time'] = time.time()
        # print self.data
        params = urllib.urlencode({'data': json.dumps(self.data)})
        # 定义一些文件头      http://127.0.0.1/Msar/saveData
        headers = {"Content-Type": "application/x-www-form-urlencoded",
                   "Connection": "Keep-Alive"}

        # 日志记录时间,用在/var/log/msar.err.log中
        logTime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
        # 与网站构建一个连接 
        urlres = urlparse.urlparse(self._url)
        try:
            conn = httplib.HTTPConnection(urlres.netloc, timeout=45)
            # 开始进行数据提交   同时也可以使用get进行     
            conn.request(method="POST", url=self._url, body=params, headers=headers)
            # 返回处理后的数据     
            response = conn.getresponse()
            # print response.read()
            # 如果返回状态不是200，则记录日志，并终止程序
            if str(response.status) != '200':
                with open('/var/log/msar.response.log', 'a+') as f:
                    f.write(logTime + '\n' + 'Server response status code is ' + str(
                        response.status) + '.\n by default it should be 200, please check out /var/log/msar.err.log ,or check remote server status ' + '\n')
                raise Exception
        # 判断是否提交成功 response.status
        except Exception, e:
            ex = traceback.format_exc()
            # 记录traceback信息
            with open('/var/log/msar.err.log', 'a+') as f:
                f.writelines([logTime + '\n', ex + '\n', '\n'])
            pass
        finally:
            conn.close()

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
            print self.data
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
                print '+' * 10, _k, '+' * 10
                self._print_mod(_v)
            else:
                # there is someting wrong!!
                continue
            print ''


    def _print_mod(self, data):
        for _k, _v in data.items():
            self.print_title_depth += 1
            if isinstance(_v, dict):
                print _k, '>' * 10
                self._print_mod(_v)
            else:
                print _k, ':', _v, '\t',
        print ''




