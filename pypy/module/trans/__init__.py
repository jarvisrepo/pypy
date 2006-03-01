from pypy.interpreter.mixedmodule import MixedModule

class Module(MixedModule):
    """Use explicit hardware-supported transactions from Python."""

    appleveldefs = {
    }

    interpleveldefs = {
        'begin'     : 'interp_trans.begin',
        'end'       : 'interp_trans.end',
        'abort'     : 'interp_trans.abort',
        'pause'     : 'interp_trans.pause',
        'unpause'   : 'interp_trans.unpause',
        'verbose'   : 'interp_trans.verbose',
        'is_active' : 'interp_trans.is_active',
    }
