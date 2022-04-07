import fnmatch
from functools import wraps

def public_method(method):
    """
    Decorator for methods that should appear in the documentation.
    """
    method._public_method = True
    return method

def submodule_method(pattern_matching):
    """
    Decorator for Module methods that can be passed to submodules
    by passing the submodule's name as first argument instead
    of the usual first argument (ie parameter_name)
    """
    def decorate(method):
        @wraps(method)
        def decorated(self, *args, **kwargs):
            name = args[0]
            if pattern_matching and ('*' in name or '[' in name):
                for n in fnmatch.filter(self.submodules.keys(), name):
                    return [getattr(self.submodules[n], method.__name__)(*args[1:], **kwargs) for n in fnmatch.filter(self.submodules.keys(), name)]\
                         + [getattr(self.submodules[self.aliases[n]], method.__name__)(*args[1:], **kwargs) for n in fnmatch.filter(self.aliases.keys(), name)]

            elif name in self.submodules or name in self.aliases:

                if name in self.aliases:
                    name = self.aliases[name]

                return getattr(self.submodules[name], method.__name__)(*args[1:], **kwargs)

            else:

                return method(self, *args, **kwargs)

        return decorated
    return decorate


def thread_locked(method):
    """
    Decorator for Module methods that shouldn't run concurrently in multiple threads.
    Wrap method in a simple lock context.
    """
    @wraps(method)
    def decorated(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    return decorated


import logging
import traceback

class TraceLogger(logging.Logger):

    def error(self, msg, *args, **kwargs):

        msg += '\nTraceback:\n%s' % ''.join(traceback.format_stack()[-5:-2])
        return super().error(msg, *args, **kwargs)

logging.setLoggerClass(TraceLogger)
