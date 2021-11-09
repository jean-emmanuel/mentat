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
            duration = duration * 60. / self.engine.tempo
        elif mode[0] != 's':
            LOGGER.error('unrecognized mode "%s" for wait()' % mode)
            return

        duration *= 1000000000 # s to ns

        while time.monotonic_ns() - self.start_time < duration:
            time.sleep(MAINLOOP_PERIOD)

        self.start_time += duration

    def wait_next_cycle(self):

        cycle_duration = self.engine.cycle_length / 2 * 60 / self.engine.tempo
        elapsed_time = (self.engine.current_time - self.engine.cycle_start_time)
        elapsed_time /= 1000000000 # ns to s
        time_before_next_cycle = cycle_duration - elapsed_time % cycle_duration

        self.wait(time_before_next_cycle, 's')
