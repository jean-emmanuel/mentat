from .utils import *

class Sequencer():
    """
    Mixin class, defines methods for starting/stopping scenes.
    """

    def __init__(self, modname):
        self.scene_namespace = modname

    @public_method
    def start_scene(self, name, scene, *args, **kwargs):
        """
        start_scene(name, scene, *args, **kwargs)

        Start scene in a thread.
        If a scene with the same name is already running, it will be stopped.
        Scenes should be implemented as methods of the object and
        can call self.wait() to create timed sequences or loops.
        Different objects may call a scene with the same name simultaneously.

        **Parameters**

        - `name`: scene name
        - `scene`: function or method
        - `*args`: arguments for the scene function
        - `**kwargs`: keyword arguments for the scene function
        """
        self.stop_scene('/%s/%s/%s' % (self.scene_namespace, self.name, name))
        self.engine.start_scene('/%s/%s/%s' % (self.scene_namespace, self.name, name), scene, *args, **kwargs)

    @public_method
    def stop_scene(self, name):
        """
        stop_scene(name)

        Stop scene thread.

        **Parameters**

        - `name`: scene name, with wildcard support
        """
        self.engine.stop_scene('/%s/%s/%s' % (self.scene_namespace, self.name, name))

    @public_method
    def wait(self, duration, mode='beats'):
        """
        wait(duration, mode='beats')

        Wait for given amount of time. Can only called in scenes.
        Subsequent calls to wait() in a scene do not drift with time
        and can be safely used to create beat sequences.
        The engine's `tempo` must be set for the `beats` mode to work.

        ```
        # Example
        beat_1()
        self.wait(1, 'b') # will wait 1 beat minus beat_1's exec time
        beat_2()
        self.wait(1, 'b') # will wait 1 beat minus beat_1 and beat_2's exec time
        ```

        **Parameters**

        - `duration`: amount of time to wait
        - `mode`: 'beats' or 'seconds' (only the first letter matters)
        """
        timer = self.engine.get_scene_timer()
        if timer:
            timer.wait(duration, mode)

    @public_method
    def wait_next_cycle(self):
        """
        wait_next_cycle()

        Wait until next cycle begins. The engine's `tempo` and `cycle_length`
        must be set and the engine's `start_cycle()` method
        must be called at the beginning of a cycle for this to work.
        """
        timer = self.engine.get_scene_timer()
        if timer:
            timer.wait_next_cycle()
