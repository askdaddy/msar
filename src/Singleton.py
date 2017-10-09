# -*- coding: utf-8 -*-
'''
Created on 2013-4-16

@author: seven
'''
class Singleton(type):
    """Sigleton Metaclass"""
    
    def __init__(cls, name, bases, dic):
        super(Singleton, cls).__init__(name, bases, dic)
        cls.instance = None
    
    def __call__(self, *args, **kwargs):
        if self.instance is None:
            self.instance = super(Singleton, self).__call__(*args, **kwargs)
        return self.instance
