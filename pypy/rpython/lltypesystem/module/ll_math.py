import math
import errno
import py
from pypy.rpython.lltypesystem import lltype, rffi
from pypy.tool.sourcetools import func_with_new_name

math_frexp = rffi.llexternal('frexp', [rffi.DOUBLE, rffi.INTP], rffi.DOUBLE,
                             sandboxsafe=True)
math_modf  = rffi.llexternal('modf',  [rffi.DOUBLE, rffi.DOUBLEP], rffi.DOUBLE,
                             sandboxsafe=True)
math_ldexp = rffi.llexternal('ldexp', [rffi.DOUBLE, rffi.INT], rffi.DOUBLE)

unary_math_functions = [
    'acos', 'asin', 'atan', 'ceil', 'cos', 'cosh', 'exp', 'fabs',
    'floor', 'log', 'log10', 'sin', 'sinh', 'sqrt', 'tan', 'tanh'
    ]

binary_math_functions = [
    'atan2', 'fmod', 'hypot', 'pow'
    ]

def ll_math_frexp(x):
    exp_p = lltype.malloc(rffi.INTP.TO, 1, flavor='raw')
    mantissa = math_frexp(x, exp_p)
    exponent = rffi.cast(lltype.Signed, exp_p[0])
    lltype.free(exp_p, flavor='raw')
    return (mantissa, exponent)

def ll_math_modf(x):
    intpart_p = lltype.malloc(rffi.DOUBLEP.TO, 1, flavor='raw')
    fracpart = math_modf(x, intpart_p)
    intpart = intpart_p[0]
    lltype.free(intpart_p, flavor='raw')
    return (fracpart, intpart)

def ll_math_ldexp(x, exp):
    _error_reset()
    r = math_ldexp(x, exp)
    _check_error(r)
    return r

def _error_reset():
    rffi.set_errno(0)

ERANGE = errno.ERANGE
def _check_error(x):
    errno = rffi.get_errno()
    if errno:
        if errno == ERANGE:
            if not x:
                raise OSError
            raise OverflowError("math range error")
        else:
            raise ValueError("math domain error")

def new_unary_math_function(name):
    c_func = rffi.llexternal(name, [rffi.DOUBLE], rffi.DOUBLE,
                             sandboxsafe=True, libraries=['m'])

    def ll_math(x):
        _error_reset()
        r = c_func(x)
        _check_error(r)
        return r

    return func_with_new_name(ll_math, 'll_math_' + name)

def new_binary_math_function(name):
    c_func = rffi.llexternal(name, [rffi.DOUBLE, rffi.DOUBLE], rffi.DOUBLE,
                             sandboxsafe=True, libraries=['m'])

    def ll_math(x, y):
        _error_reset()
        r = c_func(x, y)
        _check_error(r)
        return r

    return func_with_new_name(ll_math, 'll_math_' + name)

# the two above are almost the same, but they're C-c C-v not to go mad
# with meta-programming

for name in unary_math_functions:
    globals()['ll_math_' + name] = new_unary_math_function(name)
    
for name in binary_math_functions:
    globals()['ll_math_' + name] = new_binary_math_function(name)
    
