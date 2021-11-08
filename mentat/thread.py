from threading import Thread, current_thread
from sys import settrace

class KillableThread(Thread):
    """
    A subclass of Thread, with a kill() method.
    Original code: Connelly Barnes
    """

    def __init__(self, *args, **keywords):
        Thread.__init__(self, *args, **keywords)
        self.killed = False

    def start(self):
        """Start the thread."""
        self.__run_backup = self.run
        self.run = self.__run # Force the Thread to install our trace.
        Thread.start(self)

    def __run(self):
        """ Hacked run function, which installs the trace."""
        settrace(self.globaltrace)
        self.__run_backup()
        self.run = self.__run_backup

    def globaltrace(self, frame, why, arg):
        if why == 'call':
            return self.localtrace
        else:
            return None

    def localtrace(self, frame, why, arg):
        if self.killed:
            if why == 'line':
                raise SystemExit()
        return self.localtrace

    def kill(self):
        self.killed = True

    @staticmethod
    def get_current():
        return current_thread()
