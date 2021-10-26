import logging
LOGGER = logging.getLogger(__name__)

import time

from .config import *

class Timer():

    def __init__(self, engine):

        self.engine = engine
        self.start_time = self.engine.current_time

    def reset(self):

        self.start_time = self.engine.current_time

    def wait(self, duration, mode):

        if mode[0] == 'b':
            duration = duration * 60. / self.engine.bpm
        elif mode[0] != 's':
            LOGGER.error('unrecognized mode "%s" for wait()' % mode)
            return

        while time.time() - self.start_time < duration:
            time.sleep(MAINLOOP_PERDIO)

        self.start_time += duration
