from .utils import *
from .logger import Logger
from .sequencer import Sequencer
from .engine import Engine

class Route(Logger, Sequencer):
    """
    Routing object that processes messages received by the engine when active.

    **Instance properties**

    - `engine`: Engine instance
    """

    @public_method
    def __init__(self, name):
        """
        Route()

        Route object constructor.

        **Parameters**

        - name: roustart_scte name
        """
        self.name = name
        Logger.__init__(self, __name__)
        Sequencer.__init__(self, __name__)

        if Engine.INSTANCE is None:
            self.error('the engine must created before any module')
            raise
        else:
            self.engine = Engine.INSTANCE

    @public_method
    def activate(self):
        """
        activate()

        Called when the engine switches to this route.
        """
        pass

    @public_method
    def deactivate(self):
        """
        deactivate()

        Called when the engine switches to another route.
        """
        self.stop_scene('*')

    @public_method
    def route(self, protocol, port, address, args):
        """
        route(protocol, port, address, args)

        Process messages received by the engine.

        **Parameters**

        - protocol: 'osc' or 'midi'
        - port: name of module or port number if unknown
        - address: osc address
        - args: list of values
        """
        pass
