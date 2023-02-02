import logging
LOGGER = logging.getLogger(__name__)

import time

from .config import *

class Timer():

    def __init__(self, engine):

        self.engine = engine
        self.start_time = self.engine.current_time
        self.tempo = self.engine.tempo
        self.end_time = self.start_time
        self.is_beat_waiting = False

    def reset(self):
        """
        Called when the timer's scene is restarted
        """
        self.start_time = self.engine.current_time
        self.tempo = self.engine.tempo
        self.end_time = self.start_time
        self.is_beat_waiting = False

    def update_tempo(self):
        """
        Called when the engine's tempo has changed
        """

        new_tempo = self.engine.tempo

        if self.is_beat_waiting:
            """
            If we're currently waiting a beat-based duration,
            we need to adjust the end time
            """
            remaining_time = self.end_time - self.engine.current_time
            tempo_ratio = new_tempo / self.tempo
            self.end_time = self.engine.current_time + remaining_time / tempo_ratio

        self.tempo = new_tempo

    def wait(self, duration, mode):
        """
        wait for a given amount of time in beats or seconds
        """

        if mode[0] == 'b':
            self.is_beat_waiting = True
            duration = duration * 60. / self.engine.tempo
            duration *= 1000000000 # s to ns
        elif mode[0] == 's':
            duration *= 1000000000 # s to ns
        elif mode == 'ns':
            pass
        else:
            LOGGER.error('unrecognized mode "%s" for wait()' % mode)
            return

        self.end_time = self.start_time + duration

        while self.engine.current_time < self.end_time:
            time.sleep(MAINLOOP_PERIOD)

        self.start_time = self.end_time

        self.is_beat_waiting = False


    def get_current_cycle(self):
        """
        get engine's current cycle
        """
        elapsed_beats = (self.engine.current_time - self.engine.cycle_start_time) / 1000000000 * self.tempo / 60
        return int(elapsed_beats / self.engine.cycle_length)


    def wait_next_cycle(self):
        """
        wait until current cycle changes
        """
        start_cycle = self.get_current_cycle()
        while start_cycle == self.get_current_cycle():
            time.sleep(MAINLOOP_PERIOD)

        self.start_time = self.engine.current_time
