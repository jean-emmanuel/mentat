import logging
import traceback
import threading
import fnmatch
import os

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
            if len(args) > 0:
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


class ColoredFormatter(logging.Formatter):

    RESET_SEQ = "\033[0m"
    COLOR_SEQ = "\033[1;%dm"
    BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)

    COLORS = {
        'WARNING': YELLOW,
        'INFO': GREEN,
        'DEBUG': BLUE,
        'CRITICAL': MAGENTA,
        'ERROR': RED,
    }

    def formatMessage(self, record):
        levelname = record.levelname
        color = self.COLOR_SEQ % (30 + self.COLORS.get(levelname, 0))
        record.levelname = f"{color}{levelname.rjust(9, ":")}{self.RESET_SEQ}"
        return super().formatMessage(record)


class TraceLogger(logging.Logger):
    """
    Add backtrace to error logs
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        color_handler = logging.StreamHandler()
        color_handler.setFormatter(ColoredFormatter('%(asctime)s%(levelname)8s:%(name)s: %(message)s', '%H:%M:%S'))
        self.propagate = False
        self.addHandler(color_handler)

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

    def error(self, msg, *args, exception=False, **kwargs):

        if exception:
            msg += '\n  ' + traceback.format_exc().replace('\n','\n  ')
        else:
            msg += self.get_formatted_stack().replace('\n','\n  ')

        return super().error(msg , *args, **kwargs)

    def critical(self, msg, *args, **kwargs):

        msg += self.get_formatted_stack()
        super().critical(msg, *args, **kwargs)
        from .engine import Engine
        if Engine.INSTANCE is not None and Engine.INSTANCE.is_running:
            self.engine = Engine.INSTANCE
            Engine.INSTANCE.stop()
            if threading.main_thread() != threading.current_thread():
                raise SystemExit

logging.setLoggerClass(TraceLogger)
