from .utils import *

class Sequencer():
    """
    Mixin class, defines methods for starting/stopping scenes.
    """

    def __init__(self, namespace):
        self.scene_namespace = namespace

    @public_method
    def start_scene(self, name, scene, *args, **kwargs):
        """
        start_scene(name, scene, *args, **kwargs)

        Start scene in a thread.
        If a scene with the same name is already running, it will be stopped.
        Scenes should be implemented as methods of the object or lambda functions
        and can call self.wait() and self.play_sequence() to create timed sequences or loops.
        Different objects may call a scene with the same name simultaneously.

        **Parameters**

        - `name`: scene name
        - `scene`: function or method
        - `*args`: arguments for the scene function
        - `**kwargs`: keyword arguments for the scene function
        """
        if '*' in name or '[' in name:
            self.logger.critical('characters "*" and "[" are forbidden in scene name')

        self.stop_scene('/%s/%s' % (self.scene_namespace, name))
        self.engine.start_scene_thread('/%s/%s' % (self.scene_namespace, name), scene, *args, **kwargs)

    @public_method
    def restart_scene(self, name):
        """
        restart_scene(name)

        Restart a scene that's already running.
        Does nothing if the scene is not running.

        **Parameters**

        - `name`: scene name, with wildcard ('*') and range ('[]') support
        """
        self.engine.restart_scene_thread('/%s/%s' % (self.scene_namespace, name))

    @public_method
    def stop_scene(self, name):
        """
        stop_scene(name)

        Stop scene thread.

        **Parameters**

        - `name`: scene name, with wildcard support
        """
        self.engine.stop_scene_thread('/%s/%s' % (self.scene_namespace, name))

    @public_method
    def wait(self, duration, mode='beats'):
        """
        wait(duration, mode='beats')

        Wait for given amount of time. Can only be called in scenes.
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

    @public_method
    def play_sequence(self, sequence, loop=True):
        """
        play_sequence(sequence, loop=True)

        Play a sequence of actions scheduled on arbitrary beats.
        Can only be called in scenes.


        **Parameters**

        - `sequence`:
            - `dict` with beat numbers (1-indexed, quarter note based) as keys and lambda functions as values
            - `list` of `dict` sequences (one sequence = one bar)
            - sequences may contain an extra 'signature' string to change the time signature.
                If not provided in the first sequence, the signature takes the engine's cycle length value.
        - `loop`: if `False`, the sequence will play only once, otherwise it will loop until the scene is stopped

        **Example**

        ```
        # single-bar sequence
        play_sequence({
            'signature': '4/4',
            # beat 1
            1: lambda: guitar.set('mute', 1),
            # beat 3
            3: lambda: [guitar.set('mute', 0), guitar.set('disto', 1)],
            # "and" of beat 4
            4.5: lambda: guitar.set('disto', 0),
        })

        # multi-bar sequence
        play_sequence([
            {   # bar 1
                'signature': '4/4',
                # beat 1
                1: lambda: voice.set('autotune', 1),
            },
            {}, # bar 2 (empty)
            {   # bar 3 (empty, but in 3/4)
                'signature': '3/4',
            },
            {   # bar 4 (in 3/4 too)
                # beat 1
                1: lambda: foo.set('autotune', 0),
                # beat 3
                3: lambda: foo.set('autotune', 1),
            }
        ])
        ```
        """
        while True:

            if type(sequence) is dict:
                sequence = [sequence]

            length = self.engine.cycle_length

            for seq in sequence:
                waited = 0

                if 'signature' in seq:
                    length = self.engine.time_signature_to_quarter_notes(seq['signature'])

                for step in seq:

                    if step == 'signature':
                        continue

                    beat = float(step) - 1

                    if beat > 0:
                        delta = beat - waited
                        waited += delta
                        self.wait(delta, 'beats')

                    action = seq[step]
                    if callable(action):
                        action()

                rest = length - waited
                if rest > 0:
                    self.wait(rest)
                elif rest < 0:
                    self.logger.error('signature length overflow in bar %s (expected %s quarter notes, got %s) from sequence:\n%s' % (sequence.index(seq) + 1, length, length - rest, sequence))

            if not loop:
                break
