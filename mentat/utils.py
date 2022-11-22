import sys
import logging
import traceback
import threading
import fnmatch

from queue import Queue
from functools import wraps
from contextlib import contextmanager

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


lock = threading.RLock()
lock_timeout = 3
@contextmanager
def get_lock():
    held = lock.acquire(timeout=lock_timeout)
    try:
        yield held
    finally:
        if held:
            lock.release()
def thread_locked(method):
    """
    Decorator for Module methods that shouldn't run co>
    Wrap method in a simple lock context.
    """
    @wraps(method)
    def decorated(self, *args, **kwargs):
        with get_lock() as success:
            if success:
                return method(self, *args, **kwargs)
            else:
                self.logger.critical('deadlock while running %s() with args: %s, kwargs: %s' % (method.__name__, args, kwargs))
    return decorated

def force_mainthread(method):
    """
    Decorator for methods that should be run only in the main thread:
    when called from another thread, the method is put in a queue and
    resolved in the engine's main loop.
    """
    @wraps(method)
    def decorated(self, *args, **kwargs):
        if threading.main_thread() != threading.current_thread():
            self.action_queue.put([method, self, args, kwargs])
            return None
        else:
            return method(self, *args, **kwargs)
    return decorated


class TraceLogger(logging.Logger):
    """
    Add backtrace to error logs
    """
    def get_formatted_stack(self):
        exc_info = sys.exc_info()
        stack = traceback.extract_stack()[:-3]
        trace = traceback.format_list(stack)
        formatted = ''
        for line in trace:
            if '  File "/usr/lib' in line or '  File "<frozen' in line:
                continue
            elif 'mentat/utils.py' in line and ', in decorated' in line:
                continue
            else:
                formatted += line

        return '\nTraceback (most recent call last):\n%s' % formatted

    def error(self, msg, *args, **kwargs):

        msg += self.get_formatted_stack()
        return super().error(msg , *args, **kwargs)

    def critical(self, msg, *args, **kwargs):

        msg += self.get_formatted_stack()
        super().critical(msg, *args, **kwargs)
        raise SystemExit

logging.setLoggerClass(TraceLogger)
