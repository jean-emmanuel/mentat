from pyalsa import alsaseq
from pyalsa.alsaseq import *

MIDI_TO_OSC = {
    SEQ_EVENT_NOTEON: '/note_on',
    SEQ_EVENT_NOTEOFF: '/note_off',
    SEQ_EVENT_CONTROLLER: '/control_change',
    SEQ_EVENT_PGMCHANGE: '/program_change',
    SEQ_EVENT_PITCHBEND: '/pitch_bend',
    SEQ_EVENT_SYSEX: '/sysex',
}

OSC_TO_MIDI = {
    '/note_on': SEQ_EVENT_NOTEON,
    '/note_off': SEQ_EVENT_NOTEOFF,
    '/control_change': SEQ_EVENT_CONTROLLER,
    '/program_change': SEQ_EVENT_PGMCHANGE,
    '/pitch_bend': SEQ_EVENT_PITCHBEND,
    '/sysex': SEQ_EVENT_SYSEX,
}

def midi_to_osc(event):

    mtype = event.type

    if mtype not in MIDI_TO_OSC:
        return None

    data = event.get_data()

    osc = {}
    osc['address'] = MIDI_TO_OSC[mtype]

    if mtype == SEQ_EVENT_NOTEON:
        osc['args'] = [data['note.channel'], data['note.note'], data['note.velocity']]
    elif mtype == SEQ_EVENT_NOTEOFF:
        osc['args'] = [data['note.channel'], data['note.note'], 0]
    elif mtype == SEQ_EVENT_PITCHBEND or mtype == SEQ_EVENT_PGMCHANGE:
        osc['args'] = [data['control.channel'], data['control.value']]
    elif mtype == SEQ_EVENT_SYSEX:
        osc['args'] = data['ext']
    elif mtype == SEQ_EVENT_CONTROLLER:
        osc['args'] = [data['control.channel'], data['control.param'], data['control.value']]
    else:
        return None

    return osc

def osc_to_midi(address, args):

    if address not in OSC_TO_MIDI:
        return None

    if not all(isinstance(e, int) for e in args):
        return None

    mtype = OSC_TO_MIDI[address]
    event = alsaseq.SeqEvent(mtype)

    if mtype == SEQ_EVENT_NOTEON:
        event.set_data({'note.channel': args[0], 'note.note': args[1], 'note.velocity': args[2]})
    elif mtype == SEQ_EVENT_NOTEOFF:
        event.set_data({'note.channel': args[0], 'note.note': args[1]})
    elif mtype == SEQ_EVENT_PITCHBEND or mtype == SEQ_EVENT_PGMCHANGE:
        event.set_data({'control.channel': args[0], 'control.value': args[1]})
    elif mtype == SEQ_EVENT_SYSEX:
        event.set_data({'ext': list(args)})
    elif mtype == SEQ_EVENT_CONTROLLER:
        event.set_data({'control.channel': args[0], 'control.param': args[1], 'control.value': args[2]})
    else:
        return None

    return event
