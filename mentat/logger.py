from .utils import *
import logging

class Logger():
    """
    Mixin class, defines methods for logging.
    """

    def __init__(self, modname):
        self.logger = logging.getLogger(modname)

    @public_method
    def debug(self, message):
        """
        debug(message)

        Print a debug message, prefixed with the object's name.

        **Parameters**

        - message: debug message
        """
        self.logger.debug("%s: %s" % (self.name, message))

    @public_method
    def info(self, message):
        """
        info(message)

        Print a info message, prefixed with the object's name.

        **Parameters**

        - message: info message
        """
        self.logger.info("%s: %s" % (self.name, message))

    @public_method
    def error(self, message):
        """
        error(message)

        Print an error message, prefixed with the object's name.

        **Parameters**

        - message: error message
        """
        self.logger.error("%s: %s" % (self.name, message))
