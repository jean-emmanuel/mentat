import logging
import traceback
import threading
import fnmatch

from functools import wraps

from typing import Callable, TypeVar, ParamSpec
T = TypeVar('T')
P = ParamSpec('P')

type_callback = Callable

def public_method(method: Callable[P, T])-> Callable[P, T]:
    """
    Decorator for methods that should appear in the documentation.
    """
    method._public_method = True
    return method

def submodule_method(pattern_matching: bool) -> Callable[[Callable[P, T]], Callable[P, T] ]:
    """
    Decorator for Module methods that can be passed to submodules
    by passing the submodule's name as first argument instead
    of the usual first argument (ie parameter_name)
    """
    def decorate(method: Callable[P, T]) -> Callable[P, T]:
        @wraps(method)
        def decorated(self: int, *args: P.args, **kwargs: P.kwargs) -> T:
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


def force_mainthread(method: Callable[P, T]) -> Callable[P, T]:
    """
    Decorator for methods that should be run only in the main thread:
    when called from another thread, the method is put in a queue and
    resolved in the engine's main loop.
    """
    @wraps(method)
    def decorated(self, *args, **kwargs):
        if threading.main_thread() != threading.current_thread():
            self.engine.action_queue.put([method, self, args, kwargs])
            return None
        else:
            return method(self, *args, **kwargs)
    return decorated


class TraceLogger(logging.Logger):
    """
    Add backtrace to error logs
    """
    def get_formatted_stack(self):
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


t_mapping_params = str|tuple[str, ...]|list[str|tuple[str, ...]]
