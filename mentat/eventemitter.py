"""
EventEmitter class
"""

from .utils import public_method

class EventEmitter():
    """
    Simple event emitter
    """

    parent_module = None

    def __init__(self):

        self.event_callbacks = {}

    @public_method
    def add_event_callback(self, event, callback):
        """
        add_event_callback(event, callback)

        Bind a callback function to an event.
        See [Module](#module) and [Engine](#engine) for existing events.

        **Parameters**

        - `event`: name of event
        - `callback`: function or method.
        The callback's signature must match the event's arguments.
        """
        if event not in self.event_callbacks:
            self.event_callbacks[event] = []
        if callback not in self.event_callbacks[event]:
            self.event_callbacks[event].append(callback)

    @public_method
    def dispatch_event(self, event, *args):
        """
        dispatch_event(event, *args)

        Dispatch event to bound callback functions.
        Unless the callback returns `False`, the event will be passed
        to the module's parent until

        **Parameters**

        - `event`: name of event
        - `*args`: arguments for the callback function
        """
        bubble = True

        if event in self.event_callbacks:
            for callback in self.event_callbacks[event]:
                if callback(*args) is False:
                    bubble = False

        if bubble and self.parent_module is not None:

            self.parent_module.dispatch_event(event, *args)
