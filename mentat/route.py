from .utils import *
from .logger import Logger
from .sequencer import Sequencer

class Route(Logger, Sequencer):
    """
    Routing object that processes messages received by the engine when active.

    **Instance properties**

    - `engine`: Engine instance, available once the engine is started
    """

    @public_method
    def __init__(self, name):
        """
        Route()

        Route object constructor.

        **Parameters**

        - name: roustart_scte name
        """
        Logger.__init__(self, __name__)
        Sequencer.__init__(self, __name__)

        self.engine = None
        self.name = name

    @public_method
    def initialize(self, engine):
        """
        initialize(engine)

        Called by the engine when started.

        **Parameters**

        - engine: engine instance
        """
        self.engine = engine

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
