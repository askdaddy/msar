'''
Created on 2013-4-13

@author: seven
'''
import sys

def usage(helps):
    help = 'Usage: '
    help += 'msar [options] \n'
    help += '\noptions:\n'
    help += '\n'.join(helps)
    return help
        
ACTION_OPTIONAL = '?'
ACTION_ZERO_OR_MORE = '*'
ACTION_ONE_OR_MORE = '+'
ACTION_SWITCH = 'TF'

ARG_PREFIX = '-'

class argument(object):
    sArg = ''
    lArg = ''
    help = ''
    # action: 
    action = ''
    value = None
    def __init__(self, *args, **kwargs):
        (self.sArg, self.lArg) = args
        self.help = kwargs['help'] if kwargs.has_key('help') else ''
        self.action = kwargs['action'] if kwargs.has_key('action') else ''
    def __repr__(self, *args, **kwargs):
        return 'sArg:' + self.sArg + '|lArg:' + self.lArg
    def parse(self, args):
        if self.action == ACTION_SWITCH:
            if self.sArg in args or self.lArg in args:
                self.value = True
            else:
                self.value = False
        elif self.action == ACTION_OPTIONAL:
            for i in range(0, len(args)):
                a = args[i]
                if self.sArg == a or self.lArg == a:
                    if i + 1 < len(args):
                        self.value = args[i + 1]
            
    def format_help(self):
        help_str = '  '
        help_str += self.sArg + ',' if len(self.sArg) >= 2 else '   '
        help_str += ' ' + self.lArg
        help_str += '\t' + self.help 
        return help_str
    
    def name(self):
        return self.lArg.replace(ARG_PREFIX * 2, '')

class argparser(object):
    def __init__(self, help_information=''):
        self.args = []
        self.add_argument('-h', '--help', action=ACTION_SWITCH, help=help_information)
        
    def add_argument(self, *args, **kwargs):
        (s, l) = args
        if len(s) <= 0 and len(l) <= 0:
            return
        
        if self.has_argument(s) < 0 and self.has_argument(l) < 0:
            self.args.append(argument(*args, **kwargs))
        
    def get_helps(self):
        helps = []
        for a in self.args:
            helps.append(a.format_help())
        return helps
            
    def has_argument(self, arg):
        if len(arg) <= 0:
            return -1
        
        count = len(self.args)
        for idx in range(0, count):
            a = self.args[idx]
            if a.sArg == arg or a.lArg == arg:
                return idx
            
            prefixarg = ARG_PREFIX + arg
            if a.sArg == prefixarg or a.lArg == prefixarg:
                return idx
            
            dprefixarg = ARG_PREFIX + prefixarg
            if a.sArg == dprefixarg or a.lArg == dprefixarg:
                return idx
        return -1
    
    def get_argument(self, arg):
        idx = self.has_argument(arg)
        if idx < 0:
            self._show_usage()
        
        return self.args[idx].value
    
    def parse_argument(self, args):
        self.check_argument(args)
        for a in self.args:
            a.parse(args)
        # handle help argument first.
        if self.get_argument('-h') or self.get_argument('--help'):
            self._show_usage()
            
    def __iter__(self):
        self.step = 0
        return self    
    
    def next(self):
        if self.step == len(self.args):
            raise StopIteration
        self.step += 1
        return self.args[self.step - 1]
    
    def check_argument(self, args):
        if len(args) <= 0 :
            self._show_usage()
        
        for a in args:
            if ARG_PREFIX in a:
                if self.has_argument(a) < 0:
                    print 'ERR: argument `' + a + '` undefined.\nUse `-h` for more information'
                    sys.exit(0)
                    
    def _show_usage(self):
        print usage(self.get_helps())
        sys.exit(0)
