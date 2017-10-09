#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-
"""
Created on 2013-7-19

@author  cyrus
"""

# CSV format
# The statistics may be consulted either from the unix socket or from the HTTP page. Both means provide a CSV format whose fields follow.

# frontend：接收请求的前端虚拟节点，Frontend可以根据规则直接指定具体使用后端的 backend(可动态选择)。
# backend：后端服务集群的配置，是真实的服务器，一个Backend对应一个或者多个实体服务器。

# pxname: proxy name      代理名
# svname: service name (FRONTEND for frontend, BACKEND for backend, any name for server)  服务器名
# qcur: current queued requests   当前请求队列
# qmax: max queued requests   最大请求队列
# scur: current sessions    当前会话
# smax: max sessions     最大会话
# slim: sessions limit   会话限制
# stot: total sessions     总会话
# bin: bytes in           输入字节
# bout: bytes out          输出字节
# dreq: denied requests      拒绝的请求
# dresp: denied responses    拒绝的响应
# ereq: request errors       请求错误
# econ: connection errors    连接错误
# eresp: response errors (among which srv_abrt)    回应错误
# wretr: retries (warning)         重试错误
# wredis: redispatches (warning)       再次发送
# status: status (UP/DOWN/NOLB/MAINT/MAINT(via)...)   状态
# weight: server weight (server), total weight (backend)    服务器权重，总权重
# act: server is active (server), number of active servers (backend)    活动服务器个数
# bck: server is backup (server), number of backup servers (backend)    备份服务器个数
# chkfail: number of failed checks          失败的检查次数
# chkdown: number of UP->DOWN transitions     从UP->DOWN切换次数
# lastchg: last status change (in seconds)        最后状态改变时间
# downtime: total downtime (in seconds)            总的宕机时间(秒)
# qlimit: queue limit                   队列限制
# pid: process id (0 for first instance, 1 for second, ...)         进程id (0 第一个实例, 1 为第二个, ...)
# iid: unique proxy id             唯一代理id
# sid: service id (unique inside a proxy)           内部代理服务id
# throttle: warm up status 				服务器变热状态
# lbtot: total number of times a server was selected       服务器被选择的总次数
# tracked: id of proxy/server if tracking is enabled           
# type (0=frontend, 1=backend, 2=server, 3=socket)         类型
# rate: number of sessions per second over last elapsed second   前一秒会话数
# rate_lim: limit on new sessions per second          每秒新会话限制数
# rate_max: max number of new sessions per second         每秒新会话最大数
# check_status: status of last health check, one of:      最后一次检查健康状态
# UNK -> unknown            未知
# INI -> initializing		初始化
# SOCKERR -> socket error         socket错误
# L4OK -> check passed on layer 4, no upper layers testing enabled       
# L4TMOUT -> layer 1-4 timeout     
# L4CON -> layer 1-4 connection problem, for example "Connection refused" (tcp rst) or "No route to host" (icmp)
# L6OK -> check passed on layer 6
# L6TOUT -> layer 6 (SSL) timeout
# L6RSP -> layer 6 invalid response - protocol error
# L7OK -> check passed on layer 7
# L7OKC -> check conditionally passed on layer 7, for example 404 with disable-on-404
# L7TOUT -> layer 7 (HTTP/SMTP) timeout
# L7RSP -> layer 7 invalid response - protocol error
# L7STS -> layer 7 response error, for example HTTP 5xx
# check_code: layer5-7 code, if available
# check_duration: time in ms took to finish last health check
# hrsp_1xx: http responses with 1xx code            http 1xx 响应头数据
# hrsp_2xx: http responses with 2xx code			http 2xx 响应头数据
# hrsp_3xx: http responses with 3xx code			http 3xx 响应头数据
# hrsp_4xx: http responses with 4xx code			http 4xx 响应头数据	
# hrsp_5xx: http responses with 5xx code			http 5xx 响应头数据
# hrsp_other: http responses with other codes (protocol error)     其它响应头数据   协议错误处理
# hanafail: failed health checks details
# req_rate: HTTP requests per second over last elapsed second       HTTP请求
# req_rate_max: max number of HTTP requests per second observed      
# req_tot: total number of HTTP requests received       接受的HTTP请求总数
# cli_abrt: number of data transfers aborted by the client   客户端数据流失数
# srv_abrt: number of data transfers aborted by the server (inc. in eresp)   服务端数据流失数

from src import argparser, define
import re
from output import Output
import urllib
import traceback
import sys
import time
import commands
# from Crypto.SelfTest import SelfTestError
# from twisted.protocols.ftp import SVC_CLOSING_CTRL_CNX

class haproxy(object):
	def __init__(self, main):
	 	self.main = main
	 	main.add_argument('', '--ha', action = argparser.ACTION_SWITCH, help = 'Collect Haproxy usage')
		# 部署时将self.haproxy指向本机haproxy的csv路径
	 	# 如：self.haproxy_host = 'http://demo.1wt.eu/;csv'
	 	self.haproxy_host = 'http://127.0.0.1/admin_stats;csv'
	
	def __call__(self):
		try:
			result = commands.getoutput("ps -ef | grep haproxy | grep -v 'grep' | wc -l")
			if int(result) > 0:  # 判断本机是否运行Haproxy
				try:
					data = self.get_haproxy_dict()
					self.main.Output.outputData({self.__class__.__name__:data})
				except Exception, e:
					logTime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()))
					ex = traceback.format_exc()
					with open('/var/log/msar.haproxy.log', 'a+') as f:
						f.writelines([logTime + '\n', ex + '\n', '\n'])
					pass
			else:
				return None
		except ValueError, e:  # 捕获int(result)异常，若有则说明返回结果不是数字字符串
			return None
		
		# data = self.get_haproxy_dict()
		# self.main.Output.outputData({self.__class__.__name__:data})
	
	def get_csv(self):
		self.result = urllib.urlopen(self.haproxy_host)
		self.csv = self.result.read()
		self.csv = self.csv[1:].strip()


	def get_l(self):
		self.l = self.csv.split('\n')  # self.l是cvs文件每行组成的列表,第一项是字典的keys，以后每项是对应的数据
	
	def get_keys(self):
		self.keys = self.l[0][:-1].split(',')  # 获取所有的keys ,self.keys是一个列表

	def get_data(self):
		self.dt = []  # 存储数据项
		for each in self.l[1:]:
			self.dt.append(each[:-1].split(','))  # each的处理和keys一样
			
	# 过滤之后的信息	
	def get_dict_demo(self):
		self.dc = {}
		for each in self.dt:
			D = dict(zip(self.keys, each))
			sv = D.get('svname')
			if self.dc.has_key(sv):
				self.set_dict(sv, D)
			else:
				self.dc.setdefault(sv, {})
				self.set_dict(sv, D)
		return self.dc
			

	# 收集全部信息
	def get_dict_all(self):
		self.pxdc = {}
		# self.svdc = {}
		for each in self.dt:
			D = dict(zip(self.keys, each))
			px = D.get('pxname')
			if self.pxdc.has_key(px):
				D.pop('pxname')
				sv = D.pop('svname')
				self.pxdc[px].setdefault(sv, D)
			else:
				self.pxdc.setdefault(px, {})
				D.pop('pxname')
				sv = D.pop('svname')
				self.pxdc[px].setdefault(sv, D)

	def get_haproxy_dict(self):
 		self.get_csv()
 		self.get_l()
 		self.get_keys()
 		self.get_data()
 		# self.get_dict_all()
  		# return self.pxdc
  		self.get_dict_demo()
  		return self.dc
  	
	# 收集项目分类
	def set_dict(self, sv, D):
		self.dc[sv].setdefault('qcur', D.get('qcur'))
		self.dc[sv].setdefault('qmax', D.get('qmax'))
		self.dc[sv].setdefault('smax', D.get('smax'))
		self.dc[sv].setdefault('scur', D.get('scur'))
		self.dc[sv].setdefault('chkdown', D.get('chkdown'))
		self.dc[sv].setdefault('bin', D.get('bin'))
		self.dc[sv].setdefault('bout', D.get('bout'))
		self.dc[sv].setdefault('dreq', D.get('dreq'))
		self.dc[sv].setdefault('dresp', D.get('dresp'))
		self.dc[sv].setdefault('ereq', D.get('ereq'))
		self.dc[sv].setdefault('econ', D.get('econ'))
		self.dc[sv].setdefault('eresp', D.get('eresp'))
		self.dc[sv].setdefault('rate_max', D.get('rate_max'))
		self.dc[sv].setdefault('rate', D.get('rate'))            
