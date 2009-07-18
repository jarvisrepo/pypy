from pypy.jit.metainterp.specnode import prebuiltNotSpecNode
from pypy.jit.metainterp.specnode import FixedClassSpecNode
from pypy.jit.metainterp.specnode import VirtualInstanceSpecNode
from pypy.jit.metainterp.history import AbstractValue
from pypy.jit.metainterp.optimize import av_newdict, _findall, sort_descrs

# ____________________________________________________________

UNIQUE_UNKNOWN = '\x00'
UNIQUE_YES     = '\x01'
UNIQUE_NO      = '\x02'

class InstanceNode(object):
    """For the first phase: InstanceNode is used to match the start and
    the end of the loop, so it contains both 'origfields' that represents
    the field's status at the start and 'curfields' that represents it
    at the current point (== the end when the first phase is complete).
    """
    origfields = None   # optimization; equivalent to an empty dict
    curfields = None    # optimization; equivalent to an empty dict
    dependencies = None
    knownclsbox = None
    unique = UNIQUE_UNKNOWN   # for find_unique_nodes()

    def __init__(self, escaped, fromstart=False):
        self.escaped = escaped
        self.fromstart = fromstart

    def add_escape_dependency(self, other):
        assert not self.escaped
        if self.dependencies is None:
            self.dependencies = []
        self.dependencies.append(other)

    def mark_escaped(self):
        # invariant: if escaped=True, then dependencies is None
        if not self.escaped:
            self.escaped = True
            if self.dependencies is not None:
                deps = self.dependencies
                self.dependencies = None
                for box in deps:
                    box.mark_escaped()

    def __repr__(self):
        flags = ''
        if self.escaped:     flags += 'e'
        if self.fromstart:   flags += 's'
        if self.knownclsbox: flags += 'c'
        return "<InstanceNode (%s)>" % (flags,)


class PerfectSpecializationFinder(object):
    node_escaped = InstanceNode(escaped=True)

    def __init__(self):
        self.nodes = {}     # Box -> InstanceNode

    def getnode(self, box):
        return self.nodes.get(box, self.node_escaped)

    def find_nodes(self, loop):
        inputnodes = []
        for box in loop.inputargs:
            instnode = InstanceNode(escaped=False, fromstart=True)
            inputnodes.append(instnode)
            self.nodes[box] = instnode
        self.inputnodes = inputnodes
        #
        for op in loop.operations:
            opnum = op.opnum
            for value, func in find_nodes_ops:
                if opnum == value:
                    func(self, op)
                    break
            else:
                self.find_nodes_default(op)

    def find_nodes_default(self, op):
        if not op.has_no_side_effect():
            # default case: mark the arguments as escaping
            for box in op.args:
                self.getnode(box).mark_escaped()

    def find_nodes_NEW_WITH_VTABLE(self, op):
        instnode = InstanceNode(escaped=False)
        instnode.knownclsbox = op.args[0]
        self.nodes[op.result] = instnode

    def find_nodes_SETFIELD_GC(self, op):
        instnode = self.getnode(op.args[0])
        if instnode.escaped:
            return     # nothing to be gained from tracking the field
        fieldnode = self.getnode(op.args[1])
        field = op.descr
        assert isinstance(field, AbstractValue)
        if instnode.curfields is None:
            instnode.curfields = av_newdict()
        instnode.curfields[field] = fieldnode
        instnode.add_escape_dependency(fieldnode)

    def find_nodes_GETFIELD_GC(self, op):
        instnode = self.getnode(op.args[0])
        if instnode.escaped:
            return     # nothing to be gained from tracking the field
        field = op.descr
        assert isinstance(field, AbstractValue)
        if instnode.curfields is not None and field in instnode.curfields:
            fieldnode = instnode.curfields[field]
        elif instnode.origfields is not None and field in instnode.origfields:
            fieldnode = instnode.origfields[field]
        else:
            fieldnode = InstanceNode(escaped=False,
                                     fromstart=instnode.fromstart)
            instnode.add_escape_dependency(fieldnode)
            if instnode.origfields is None:
                instnode.origfields = av_newdict()
            instnode.origfields[field] = fieldnode
        self.nodes[op.result] = fieldnode

    def find_nodes_GETFIELD_GC_PURE(self, op):
        self.find_nodes_GETFIELD_GC(op)

    def find_nodes_GUARD_CLASS(self, op):
        instbox = op.args[0]
        clsbox = op.args[1]
        try:
            instnode = self.nodes[instbox]
        except KeyError:
            instnode = self.nodes[instbox] = InstanceNode(escaped=True)
        assert instnode is not self.node_escaped
        assert (instnode.knownclsbox is None or
                instnode.knownclsbox.equals(clsbox))
        instnode.knownclsbox = clsbox

    def find_nodes_JUMP(self, op):
        """Build the list of specnodes based on the result
        computed by this PerfectSpecializationFinder.
        """
        for box in op.args:
            self.find_unique_nodes(self.getnode(box))
        specnodes = []
        assert len(self.inputnodes) == len(op.args)
        for i in range(len(op.args)):
            inputnode = self.inputnodes[i]
            exitnode = self.getnode(op.args[i])
            specnodes.append(self.intersect(inputnode, exitnode))
        self.specnodes = specnodes

    def find_unique_nodes(self, exitnode):
        if (exitnode.escaped or exitnode.fromstart
            or exitnode.knownclsbox is None
            or exitnode.unique != UNIQUE_UNKNOWN):
            # the exitnode is not suitable for being a virtual, or we
            # encounter it more than once when doing the recursion
            exitnode.unique = UNIQUE_NO
        else:
            exitnode.unique = UNIQUE_YES
            if exitnode.curfields is not None:
                for subnode in exitnode.curfields.values():
                    self.find_unique_nodes(subnode)

    def intersect(self, inputnode, exitnode):
        assert inputnode.fromstart
        if exitnode.unique == UNIQUE_NO or inputnode.escaped:
            # give a NotSpecNode or a FixedClassSpecNode
            if (inputnode.knownclsbox is not None and
                exitnode.knownclsbox is not None and
                inputnode.knownclsbox.equals(exitnode.knownclsbox)):
                # the class is known at the end, needed at the input,
                # and matches
                return FixedClassSpecNode(inputnode.knownclsbox)
            else:
                return prebuiltNotSpecNode
        #
        assert exitnode.unique == UNIQUE_YES
        if (inputnode.knownclsbox is not None and
            not inputnode.knownclsbox.equals(exitnode.knownclsbox)):
            # unique match, but the class is known to be a mismatch
            return prebuiltNotSpecNode
        #
        fields = []
        d = exitnode.curfields
        if d is not None:
            lst = d.keys()
            sort_descrs(lst)
            for ofs in lst:
                try:
                    if inputnode.origfields is None:
                        raise KeyError
                    node = inputnode.origfields[ofs]
                except KeyError:
                    # field stored at exit, but not read at input.  Must
                    # still be allocated, otherwise it will be incorrectly
                    # uninitialized after a guard failure.
                    node = InstanceNode(escaped=False, fromstart=True)
                specnode = self.intersect(node, d[ofs])
                fields.append((ofs, specnode))
        return VirtualInstanceSpecNode(exitnode.knownclsbox, fields)

find_nodes_ops = _findall(PerfectSpecializationFinder, 'find_nodes_')
