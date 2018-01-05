"""
Created on 11/11/2017

@author: seven
"""
import abc
import six


@six.add_metaclass(abc.ABCMeta)
class IPlugin(object):
    @abc.abstractmethod
    def constructor(self, ICop):
        pass

    @abc.abstractmethod
    def run(self):
        pass
