from .utils import *

class Route():

    @public_method
    def __init__(self, name):
        """
        Route()

        Route object constructor.

        **Parameters**

        - name: route name
        """
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

    @public_method
    def start_scene(self, name, scene, *args, **kwargs):
        """
        start_scene(name, scene, *args, **kwargs)

        Start scene in a thread.
        If a scene with the same name is already running, it will be stopped.
        Scenes should be implemented as methods of the Route object and
        can call self.wait() to create timed sequences or loops.

        **Parameters**

        - name: scene name
        - scene: function or method
        - *args: arguments for the scene function
        - *kwargs: keyword arguments for the scene function
        """
        self.stop_scene('/route/%s/%s' % (self.name, name))
        self.engine.start_scene('/route/%s/%s' % (self.name, name), scene, *args, **kwargs)

    @public_method
    def stop_scene(self, name):
        """
        stop_scene(name, scene, *args, **kwargs)

        Stop scene thread.

        **Parameters**

        - name: scene name, with wildcard support
        - scene: function or method
        """
        self.engine.stop_scene('/route/%s/%s' % (self.name, name))

    @public_method
    def wait(self, duration, mode='beats'):
        """
        wait(duration, mode='beats')

        Wait for given amount of time. Can only called in scenes.
        Subsequent calls to wait() in a scene do not drift with time
        and can be safely used to create beat sequences.

        ```
        # Example
        beat_1()
        self.wait(1, 'b') # will wait 1 beat minus beat_1's exec time
        beat_2()
        self.wait(1, 'b') # will wait 1 beat minus beat_1 and beat_2's exec time
        ```

        **Parameters**

        - duration: amount of time to wait
        - mode: 'beats' or 'seconds' (only the first letter matters)
        """
        timer = self.engine.get_scene_timer()
        if timer:
            timer.wait(duration, mode)
