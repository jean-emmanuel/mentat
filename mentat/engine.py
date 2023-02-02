import time
import liblo
import queue
import fnmatch
import atexit
import sys
import os
import pyinotify
import logging
import threading

from pyalsa import alsaseq
from signal import signal, SIGINT, SIGTERM
from queue import Queue
from pathlib import Path
from contextlib import contextmanager

from .config import *
from .utils import *
from .midi import osc_to_midi, midi_to_osc
from .thread import KillableThread as Thread
from .timer import Timer
from .module import Module

class Engine(Module):
    """
    Main object. Singleton that must be instanciated before any `Module` or `Route` object.
    The global engine instance is always accessible via `Engine.INSTANCE`.

    The engine is also a `Module` instance and can use the methods of this class.

    **Instance properties**

    - `modules`: `dict` containing modules added to the engine with names as keys
    - `routes`: `dict` containing routes added to the engine with names as keys
    - `active_route`: active route object (`None` by default)
    - `restarted`: `True` if the engine was restarted using `autorestart()`
    - `logger`: python logger
    - `tempo`: beats per minute
    - `cycle_length`: quarter notes per cycle
    - `port`: osc (udp) input port number
    - `tcp_port`: osc (tcp) input port number
    - `unix_port`: osc (unix) input socket path
    """

    INSTANCE = None

    @public_method
    def __init__(self, name, port, folder, debug=False, tcp_port=None, unix_port=None):
        """
        Engine(name, port, folder, debug=False, tcp_port=None, unix_port=None)

        Engine constructor.

        **Parameters**

        - `name`: client name
        - `port`: osc (udp) input port number
        - `folder`: path to config folder where state files will be saved to and loaded from
        - `debug`: set to True to enable debug messages and i/o statistics
        - `tcp_port`: osc (tcp) input port number
        - `unix_port`: osc (unix) input socket path
        """
        self.logger = logging.getLogger(__name__).getChild(name)
        self.name = name

        self.port = port
        self.tcp_port = tcp_port
        self.unix_port = unix_port

        if Engine.INSTANCE is not None:
            self.logger.critical('only one instance Engine can be created')
        else:
            Engine.INSTANCE = self

        logging.basicConfig(level=logging.DEBUG if debug else logging.INFO)

        self.osc_server = None
        self.osc_tcp_server = None
        self.osc_unix_server = None

        self.osc_inputs = {'osc':{}, 'osc.tcp': {}, 'osc.unix': {}}
        self.osc_outputs = {'osc': {}, 'osc.tcp': {}, 'osc.unix': {}}

        self.midi_server = None
        self.midi_ports = {}

        self.routes = {}
        self.active_route = None

        self.scenes = {}
        self.scenes_timers = {}

        self.is_running = False
        self.is_restarting = False

        self.current_time = time.monotonic_ns()
        self.cycle_start_time = self.current_time
        self.cycle_length = 4.0
        self.tempo = 120.0

        self.fastforwarding = False
        self.fastforward_frametime = False
        self.fastforward_frames = 0
        self.time_offset = 0

        self.folder = Path(folder).expanduser().resolve()

        self.modules = {}
        self.event_callbacks = {}
        self.message_queue = Queue()

        self.dirty_modules = Queue()
        self.animating_modules = []

        self.message_queue = Queue()
        self.action_queue = Queue()

        self.notifier = None
        self.restarted = os.getenv('MENTAT_RESTART') is not None

        self.log_statistics = debug
        self.statistics_time = 0
        self.statistics = {
            'midi_in': 0,
            'midi_out': 0,
            'osc_in': 0,
            'osc_out': 0,
            'exec_time': [0, 0, 0] # max, total, iterations
        }

        self.main_loop_lock = threading.RLock()

        Module.__init__(self, name)

    # backward compat
    def get_root_module(self):
        self.logger.warning('root_module property is deprecated, use engine instance directly instead')
        return self
    root_module = property(get_root_module)

    def start_servers(self):
        """
        start_servers()

        Starts osc servers and open midi ports
        """

        self.osc_server = liblo.Server(self.port, proto=liblo.UDP)
        self.osc_server.add_method(None, None, self.route_osc)

        if self.tcp_port:
            self.osc_tcp_server = liblo.Server(self.tcp_port, proto=liblo.TCP)
            self.osc_tcp_server.add_method(None, None, self.route_osc)

        if self.unix_port:
            self.osc_unix_server = liblo.Server(self.unix_port, proto=liblo.UNIX)
            self.osc_unix_server.add_method(None, None, self.route_osc)

        self.midi_server = alsaseq.Sequencer(clientname=self.name)
        for module_name in self.midi_ports:
            self.midi_ports[module_name] = self.midi_server.create_simple_port(module_name, alsaseq.SEQ_PORT_TYPE_MIDI_GENERIC | alsaseq.SEQ_PORT_TYPE_APPLICATION, alsaseq.SEQ_PORT_CAP_WRITE | alsaseq.SEQ_PORT_CAP_SUBS_WRITE | alsaseq.SEQ_PORT_CAP_READ | alsaseq.SEQ_PORT_CAP_SUBS_READ)

    def stop_servers(self):
        """
        stop_servers()

        Stop osc servers and close midi ports
        """

        if self.osc_server:
            self.osc_server.free()
            self.osc_server = None

        if self.osc_tcp_server:
            self.osc_tcp_server.free()
            self.osc_tcp_server = None

        if self.osc_unix_server:
            self.osc_unix_server.free()
            self.osc_unix_server = None

        self.midi_server = None

    def poll_servers(self):
        """
        poll_servers()

        Process incoming osc and midi messages
        """
        # process osc messages
        while self.osc_server and self.osc_server.recv(0):
            pass
        while self.osc_tcp_server and self.osc_tcp_server.recv(0):
            pass
        while self.osc_unix_server and self.osc_unix_server.recv(0):
            pass

        # process midi messages
        if self.midi_server:
            midi_events = self.midi_server.receive_events()
            for e in midi_events:
                self.route_midi(e)

    @public_method
    def start(self):
        """
        start()

        Start engine. This is usually the last statement in the script as
        it starts the processing loop that keeps the engine running.
        """
        if self.is_running:
            self.logger.error('already started')
            return

        if threading.main_thread() == threading.current_thread():
            signal(SIGINT, lambda a,b: self.stop())
            signal(SIGTERM, lambda a,b: self.stop())
        else:
            self.logger.warning('started in a thread')

        self.start_servers()

        self.current_time = time.monotonic_ns()

        if self.active_route:
            self.active_route.activate()

        self.is_running = True

        last_animation = 0
        animation_period = ANIMATION_PERIOD * 1000000

        self.logger.info('started')
        self.dispatch_event('started')

        while self.is_running:

            with self.main_loop_lock:

                self.current_time = time.monotonic_ns() + self.time_offset

                if self.fastforwarding:
                    self.time_offset += self.fastforward_frametime
                    self.fastforward_frames -= 1
                    if self.fastforward_frames == 0:
                        self.fastforwarding = False

                self.poll_servers()

                # update animations
                if self.current_time - last_animation >= ANIMATION_PERIOD:
                    last_animation = self.current_time
                    for mod in self.animating_modules:
                        mod.update_animations()
                        if not mod.animations:
                            self.animating_modules.remove(mod)

                # update parameters and queue messages
                while not self.dirty_modules.empty():
                    mod = self.dirty_modules.get()
                    mod.update_dirty_parameters()

                # resolve pending actions
                while not self.action_queue.empty():
                    method, _self, args, kwargs = self.action_queue.get()
                    method(_self, *args, **kwargs)

                # send pending messages
                self.flush()

                # statistics
                if self.log_statistics:
                    current_time = self.current_time - self.time_offset
                    self.statistics['exec_time'][0] = max(time.monotonic_ns() - current_time, self.statistics['exec_time'][0])
                    self.statistics['exec_time'][1] += time.monotonic_ns() - current_time
                    self.statistics['exec_time'][2] += 1
                    if self.statistics_time == 0:
                        self.statistics_time = current_time
                    if current_time - self.statistics_time >= 1000000000:
                        for stat in self.statistics:
                            if stat == 'exec_time':
                                peak_time = self.statistics['exec_time'][0] / 1000000
                                average_time = self.statistics['exec_time'][1] / self.statistics['exec_time'][2] / 1000000
                                self.logger.info('statistic: main loop exec time: peak %.3fms, average %.3fms' % (peak_time, average_time))
                                self.statistics['exec_time'] = [0, 0, 0]
                            elif self.statistics[stat] != 0:
                                self.logger.info('statistic: %s: %i in 1s' % (stat, self.statistics[stat]))
                                self.statistics[stat] = 0
                        self.statistics_time = current_time

                # restart ?
                if self.is_restarting:
                    self._restart()

                # take some rest
                time.sleep(MAINLOOP_PERIOD)

        self.logger.info('stopped')
        self.dispatch_event('stopped')


    @public_method
    def stop(self):
        """
        stop()

        Stop engine. This is called automatically when the process
        is terminated or when the engine restarts.
        """

        self.logger.info('stopping...')
        self.dispatch_event('stopping')
        self.is_running = False
        self.stop_scene_thread('*')
        self.stop_servers()
        if self.notifier:
            try:
                self.notifier.stop()
                self.notifier = None
            except:
                pass

    @public_method
    def restart(self):
        """
        restart()

        Stop the engine and restart once the process is terminated.
        """
        self.is_restarting = True
        self.logger.info('restarting...')
        self.dispatch_event('restarting')

    def _restart(self):
        def restart_python():
            os.environ['MENTAT_RESTART'] = '1'
            os.execl(sys.executable, sys.executable, *sys.argv)
        atexit.register(restart_python)
        self.stop()

    @public_method
    def autorestart(self):
        """
        autorestart()

        Enable engine autorestart. This watches the main python script
        and all imported modules that are located in the same directoty.
        Whenever a file is modified, the engine is restarted.
        """
        wm = pyinotify.WatchManager()
        self.notifier = pyinotify.ThreadedNotifier(wm)
        base_dir = os.path.dirname(os.path.abspath(sys.modules['__main__'].__file__))
        # add watches for imported modules
        for m in sys.modules.values():
            # builtin modules don't have a __file__ attribute
            if hasattr(m, '__file__') and m.__file__ is not None:
                f = os.path.abspath(m.__file__)
                # only watch file if it's in the same directory as the main script
                # + module src files
                if f.startswith(base_dir)  or 'mentat' in m.__name__:
                    wm.add_watch(f, pyinotify.IN_MODIFY, lambda e: self.restart())
        self.notifier.start()

    @public_method
    def add_module(self, module):
        """
        add_module(module)

        Add a module. This method will create midi ports if the module's protocol is 'midi'.

        **Parameters**

        - `module`: Module object
        """
        if module == self:
            self.logger.critical('cannot add self as module')

        self.modules[module.name] = module
        self.submodules[module.name] = module
        module.parent_module = self

        if module.port is not None:
            if module.protocol in ['osc', 'osc.tcp', 'osc.unix']:
                self.osc_inputs[module.protocol][module.port] = module.name
                self.osc_outputs[module.protocol][module.name] = module.port
            elif module.protocol == 'midi':
                self.midi_ports[module.name] = None


        self.dispatch_event('module_added', self, module)

    def add_submodule(self, *args, **kwargs):
        """
        Bypass Module.add_submodule()
        """
        self.add_module(*args, **kwargs)

    def flush(self):
        """
        flush()

        Send messages in queue.
        """
        if self.is_running:

            while not self.message_queue.empty():
                message = self.message_queue.get()
                self.send(*message)

            self.midi_server.sync_output_queue()

    @public_method
    def send(self, protocol, port, address, *args):
        """
        send(protocol, port, address, *args)

        Send OSC / MIDI message.

        **Parameters**

        - `protocol`: 'osc', 'osc.tcp', 'osc.unix' or 'midi'
        - `port`:
            module name, port number ('osc' protocol only) or unix socket path ('osc.unix' protocol only)
        - `address`: osc address
        - `args`: values or (typetag, value) tuples
        """
        if not self.is_running:
            # in case a module calls this method directly
            # before the server is started
            message = [protocol, port, address, *args]
            self.message_queue.put(message)
            return

        if protocol in ['osc', 'osc.tcp', 'osc.unix']:

            if port in self.osc_outputs[protocol]:
                port = self.osc_outputs[protocol][port]
            if protocol == 'osc':
                self.osc_server.send(port, address, *args)
            elif protocol == 'osc.tcp':
                self.osc_tcp_server.send(port, address, *args)
            elif protocol == 'osc.unix':
                self.osc_unix_server.send(port, address, *args)
            else:
                return

            if self.log_statistics:
                self.statistics['osc_out'] += 1

        elif protocol == 'midi':

            if port in self.midi_ports:

                try:
                    midi_event = osc_to_midi(address, args)
                except Exception as e:
                    self.logger.error('failed to generate midi event %s %s\n%s' % (address, args, e))
                    midi_event = None

                if midi_event:
                    midi_event.source = (self.midi_server.client_id, self.midi_ports[port])
                    self.midi_server.output_event(midi_event)
                    self.midi_server.drain_output()
                    if self.log_statistics:
                        self.statistics['midi_out'] += 1

        else:

            self.logger.error('unknown protocol %s' % protocol)

    @public_method
    def add_route(self, route):
        """
        add_route(route)

        Add a route.

        **Parameters**

        - `route`: Route object
        """
        self.routes[route.name] = route
        self.dispatch_event('route_added', route)

    @public_method
    @force_mainthread
    def set_route(self, name):
        """
        set_route(name)

        Set active route.

        **Parameters**

        - `name`: route name
        """
        if name in self.routes:
            if self.active_route and self.is_running:
                self.active_route.deactivate()
            self.active_route = self.routes[name]
            if self.is_running:
                self.active_route.activate()
            self.logger.info('active route set to "%s"' % name)
            self.dispatch_event('route_changed', self.active_route)
        else:
            self.logger.error('route "%s" not found' % name)

    @public_method
    def route(self, protocol, port, address, args):
        """
        route(protocol, port, address, args)

        Unified route for osc and midi messages, called when the engine
        receives a midi or osc message. Messages are processed this way :

        1. If the message is sent from a port that matches a module's,
        the message is passed to that module's route method. If it
        returns `False`, further processing is prevented.

        2. If the address matches a command as per the generic control API,
        further processing is prevented.

        3. If a route is active, the message is passed to that route's
        route method.

        **Parameters**

        - `protocol`: 'osc', 'osc.tcp' or 'midi'
        - `port`: name of module or port number if unknown
        - `address`: osc address
        - `args`: list of values
        """
        if port in self.modules:
            if self.modules[port].route(address, args) == False:
                return

        if protocol != 'midi':
            if self.route_generic_osc_api(address, args) == False:
                return

        if self.active_route:
            self.active_route.route(protocol, port, address, args)

    def route_osc(self, address, args, types, src):
        """
        Route incoming raw osc events.
        """
        proto = 'osc'
        port = src.port
        if src.protocol == liblo.TCP:
            proto = 'osc.tcp'
        elif src.protocol == liblo.UNIX:
            proto = 'osc.unix'
        if src.port in self.osc_inputs[proto]:
            port = self.osc_inputs[proto][src.port]
        self.route(proto, port, address, args)
        if self.log_statistics:
            self.statistics['osc_in'] += 1

    def route_midi(self, event):
        """
        Route incoming raw midi events.
        """
        port = self.midi_server.get_port_info(event.dest[1],event.dest[0])['name']
        osc_message = midi_to_osc(event)
        if osc_message:
            osc_message['port'] = port
            self.route('midi', port, osc_message['address'], osc_message['args'])
            if self.log_statistics:
                self.statistics['midi_in'] += 1

    def route_generic_osc_api(self, address, args):
        """
        Generic OSC API: control any parameter or call any module method

        **Parameters**

        - `address`: osc address
        - `args`: list of values

        **Returns*
        `False` if a module parameter or method was reached, `True` otherwise.
        """
        module_path = address.split('/')[1:]
        module_name = module_path[0]

        if len(module_path) < 2 or module_path[0] != self.name:
            return True

        method_name = module_path[-1]
        module_path = module_path[:-1]
        module = self

        if len(module_path) > 1:
            module_name = module_path[1]
            if module_name in self.modules:
                module = self.modules[module_name]
                for n in module_path[2:]:
                    if n in module.submodules:
                        module = module.submodules[n]
                    else:
                        module = None
                        break
            else:
                module = None

        if module is not None:

            if hasattr(module, method_name):
                method = getattr(module, method_name)
                # only allow public methods and user-defined methods
                if callable(method) and (
                        hasattr(method, '_public_method') or
                        method.__qualname__.split('.')[0] not in ['Engine', 'Module', 'Route', 'Sequencer']
                    ):
                    method(*args)


            return False

        else:

            return True

    def start_scene_thread(self, name, scene, *args, **kwargs):
        """
        start_scene_thread(scene)

        Start function in a thread.
        If a scene with the same name is already running, it will be stopped.

        **Parameters**

        - `name`: scene name
        - `scene`: function or method
        - `*args`: arguments for the scene function
        - `*kwargs`: keyword arguments for the scene function
        """
        self.stop_scene_thread(name)
        self.scenes_timers[name] = Timer(self)
        self.scenes[name] = Thread(target=scene, name=name, args=args, kwargs=kwargs)
        self.scenes[name].start()
        self.logger.debug('starting scene %s' % name)

    def restart_scene_thread(self, name):
        """
        restart_scene_thread(name)

        Restart a scene that's already running.
        Does nothing if the scene is not running.

        **Parameters**

        - `name`: scene name, with wildcard support
        """
        if '*' in name or '[' in name:
            for n in fnmatch.filter(self.scenes.keys(), name):
                self.restart_scene_thread(n)
        elif name in self.scenes and self.scenes[name].is_alive():
            self.scenes[name].kill()
            self.scenes_timers[name].reset()
            self.scenes[name].start()
            self.logger.debug('restarting scene %s' % name)

    def stop_scene_thread(self, name):
        """
        stop_scene_thread(scene)

        Stop scene thread.

        **Parameters**

        - `name`: scene name
        - `scene`: function or method
        """
        if '*' in name or '[' in name:
            for n in fnmatch.filter(self.scenes.keys(), name):
                self.stop_scene_thread(n)
        elif name in self.scenes:
            if self.scenes[name].is_alive():
                self.logger.debug('stopping scene %s' % name)
                self.scenes[name].kill()
            else:
                self.logger.debug('cleaning scene %s' % name)
            id = self.scenes[name].ident
            del self.scenes[name]
            del self.scenes_timers[name]

    def get_scene_timer(self):
        """
        get_scene_timer()

        Threaded scenes each have a Timer object they can use to wait().
        Route objects can call self.wait(), but it is forbidden in the main thread.
        """
        name = Thread.get_current().name
        if name in self.scenes_timers:
            return self.scenes_timers[name]
        else:
            self.logger.error('cannot call wait() from main thread')
            return None

    def get_main_loop_lock(self):
        """
        get_main_loop_lock()

        Return main loop lock

        **Return**

        threading.RLock instance
        """
        name = Thread.get_current().name
        if name in self.scenes_timers:
            return self.main_loop_lock
        else:
            self.logger.error('cannot call lock() from main thread')
            # return cheap no-op context
            return memoryview(b'')

    @public_method
    def set_tempo(self, bpm):
        """
        set_tempo(bpm)

        Set engine tempo.

        **Parameters**

        - `bpm`: beats per minute
        """
        self.tempo = max(float(bpm), 0.001)
        for name in self.scenes_timers:
            self.scenes_timers[name].update_tempo()

    @public_method
    def set_cycle_length(self, quarter_notes):
        """
        set_cycle_length(quarter_notes)

        Set engine cycle (measure) length in quarter notes.

        **Parameters**

        - `quarter_notes`: quarter notes per cycle (decimals allowed)
        """
        self.cycle_length = float(quarter_notes)

    def time_signature_to_quarter_notes(self, signature):
        """
        Convert time signature string to quarter notes.
        """
        beats, unit = signature.split('/')
        mutliplier = 4 / float(unit)
        return float(beats) * mutliplier

    @public_method
    def set_time_signature(self, signature):
        """
        set_time_signature(signature)

        Set engine cycle (measure) length from a musical time signature.

        **Parameters**

        - `signature`: `string` like '4/4', '5/4', '7/8'...
        """
        self.set_cycle_length(self.time_signature_to_quarter_notes(signature))

    @public_method
    def start_cycle(self):
        """
        start_cycle()

        Set current time as cycle start.
        Affects Route.wait_next_cycle() method.
        """
        self.cycle_start_time = self.current_time

    @public_method
    def fastforward(self, duration, mode='beats'):
        """
        fastforward(amount, mode='beats')

        /!\ Experimental /!\

        Increment current time by a number of beats or seconds.
        All parameter animations and wait() calls will be affected.

        **Parameters**

        - `duration`: number of beats or seconds
        - `mode`: 'beats' or 'seconds' (only the first letter matters)
        """
        if type(duration) not in (int, float) or duration <= 0:
            self.error('fastforward: duration must be a positive number')
            return
        if self.fastforwarding:
            self.error('fastforward: already busy')
            return


        if mode[0] == 'b':
            duration = duration * 60. / self.tempo
            duration *= 1000000000 # s to ns
        elif mode[0] == 's':
            duration *= 1000000000 # s to ns

        self.fastforward_frames = 100
        self.fastforward_frametime = duration / self.fastforward_frames
        self.fastforwarding = True

    def advance_timers(self):

        for timer in self.scenes_timers.values():
            timer.start_time += duration
        for mod in self.animating_modules:
            for param in mod.animations:
                param.animate_start += duration

    def register_event_callback(self, event, callback):
        """
        register_event_callback(event, callback)

        See module.add_event_callback()
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

        **Parameters**

        - `event`: name of event
        - `*args`: arguments for the callback function
        """
        if event in self.event_callbacks:
            for callback in self.event_callbacks[event]:
                callback(*args)
