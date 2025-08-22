import logging

from typing import TYPE_CHECKING

from .utils import public_method
from .sequencer import Sequencer
from .engine import Engine

class Route(Sequencer):
    """
    Routing object that processes messages received by the engine when active.

    **Instance properties**

    - `engine`: Engine instance
    - `logger`: python logger
    """
    if TYPE_CHECKING:
        from .engine import Engine
        engine: Engine
        
    @public_method
    def __init__(self, name: str):
        """
        Route(name)

        Route object constructor.

        **Parameters**

        - `name`: route name
        """
        self.logger = logging.getLogger(self.__class__.__name__).getChild(name)
        self.name = name

        Sequencer.__init__(self, 'route/' + self.name)

        if Engine.INSTANCE is None:
            self.logger.critical('the engine must created before any module')
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
    def route(self,
              protocol: str,
              port: str|int,
              address: str,
              args: list|tuple):
        """
        route(protocol, port, address, args)

        Process messages received by the engine.

        **Parameters**

        - `protocol`: 'osc', 'osc.tcp' or 'midi'
        - `port`: name of module or port number if unknown
        - `address`: osc address
        - `args`: list of values
        """
        pass
