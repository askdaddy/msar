"""
Created on 11/11/2017

@author: seven
"""
import abc

import six


@six.add_metaclass(abc.ABCMeta)
class ICop(object):
    @abc.abstractmethod
    def add_argument(self, *args, **kwargs):
        pass

    @abc.abstractmethod
    def out(self, dict_data):
        pass

    @abc.abstractproperty
    def args(self):
        pass
