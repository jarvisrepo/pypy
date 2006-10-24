from __future__ import division
import py
from random import random, randint
from pypy.rpython.rlong import rlong, SHIFT, MASK
from pypy.rpython import rlong as lobj
from pypy.rpython.rarithmetic import r_uint
import operator, sys

class TestRLong(object):
    def test_simple(self):
        for op1 in [-2, -1, 0, 1, 2, 50]:
            for op2 in [-2, -1, 0, 1, 2, 50]:
                rl_op1 = rlong.fromint(op1)
                rl_op2 = rlong.fromint(op2)
                for op in "add sub mul".split():
                    r1 = getattr(rl_op1, op)(rl_op2)
                    r2 = getattr(operator, op)(op1, op2)
                    assert r1.tolong() == r2
            
    def test_floordiv(self):
        for op1 in [-12, -2, -1, 1, 2, 50]:
            for op2 in [-4, -2, -1, 1, 2, 8]:
                rl_op1 = rlong.fromint(op1)
                rl_op2 = rlong.fromint(op2)
                r1 = rl_op1.floordiv(rl_op2)
                r2 = op1 // op2
                assert r1.tolong() == r2

    def test_truediv(self):
        for op1 in [-12, -2, -1, 1, 2, 50]:
            for op2 in [-4, -2, -1, 1, 2, 8]:
                rl_op1 = rlong.fromint(op1)
                rl_op2 = rlong.fromint(op2)
                r1 = rl_op1.truediv(rl_op2)
                r2 = op1 / op2
                assert r1 == r2

    def test_mod(self):
        for op1 in [-50, -12, -2, -1, 1, 2, 50, 52]:
            for op2 in [-4, -2, -1, 1, 2, 8]:
                rl_op1 = rlong.fromint(op1)
                rl_op2 = rlong.fromint(op2)
                r1 = rl_op1.mod(rl_op2)
                r2 = op1 % op2
                assert r1.tolong() == r2

    def test_pow(self):
        for op1 in [-50, -12, -2, -1, 1, 2, 50, 52]:
            for op2 in [0, 1, 2, 8, 9, 10, 11]:
                rl_op1 = rlong.fromint(op1)
                rl_op2 = rlong.fromint(op2)
                r1 = rl_op1.pow(rl_op2)
                r2 = op1 ** op2
                assert r1.tolong() == r2

    def test_touint(self):
        import sys
        from pypy.rpython.rarithmetic import r_uint
        result = r_uint(sys.maxint + 42)
        rl = rlong.fromint(sys.maxint).add(rlong.fromint(42))
        assert rl.touint() == result

def gen_signs(l):
    for s in l:
        if s == 0:
            yield s
        else:
            yield s
            yield -s


class Test_rlong(object):

    def test_args_from_long(self):
        BASE = 1 << SHIFT
        assert rlong.fromlong(0).eq(rlong([0], 0))
        assert rlong.fromlong(17).eq(rlong([17], 1))
        assert rlong.fromlong(BASE-1).eq(rlong([BASE-1], 1))
        assert rlong.fromlong(BASE).eq(rlong([0, 1], 1))
        assert rlong.fromlong(BASE**2).eq(rlong([0, 0, 1], 1))
        assert rlong.fromlong(-17).eq(rlong([17], -1))
        assert rlong.fromlong(-(BASE-1)).eq(rlong([BASE-1], -1))
        assert rlong.fromlong(-BASE).eq(rlong([0, 1], -1))
        assert rlong.fromlong(-(BASE**2)).eq(rlong([0, 0, 1], -1))
#        assert rlong.fromlong(-sys.maxint-1).eq(
#            rlong.digits_for_most_neg_long(-sys.maxint-1), -1)

    def test_args_from_int(self):
        BASE = 1 << SHIFT
        assert rlong.fromrarith_int(0).eq(rlong([0], 0))
        assert rlong.fromrarith_int(17).eq(rlong([17], 1))
        assert rlong.fromrarith_int(BASE-1).eq(rlong([BASE-1], 1))
        assert rlong.fromrarith_int(BASE).eq(rlong([0, 1], 1))
        assert rlong.fromrarith_int(BASE**2).eq(rlong([0, 0, 1], 1))
        assert rlong.fromrarith_int(-17).eq(rlong([17], -1))
        assert rlong.fromrarith_int(-(BASE-1)).eq(rlong([BASE-1], -1))
        assert rlong.fromrarith_int(-BASE).eq(rlong([0, 1], -1))
        assert rlong.fromrarith_int(-(BASE**2)).eq(rlong([0, 0, 1], -1))
#        assert rlong.fromrarith_int(-sys.maxint-1).eq((
#            rlong.digits_for_most_neg_long(-sys.maxint-1), -1)

    def test_args_from_uint(self):
        BASE = 1 << SHIFT
        assert rlong.fromrarith_int(r_uint(0)).eq(rlong([0], 0))
        assert rlong.fromrarith_int(r_uint(17)).eq(rlong([17], 1))
        assert rlong.fromrarith_int(r_uint(BASE-1)).eq(rlong([BASE-1], 1))
        assert rlong.fromrarith_int(r_uint(BASE)).eq(rlong([0, 1], 1))
        assert rlong.fromrarith_int(r_uint(BASE**2)).eq(rlong([0, 0, 1], 1))
        assert rlong.fromrarith_int(r_uint(sys.maxint)).eq(
            rlong.fromint(sys.maxint))
        assert rlong.fromrarith_int(r_uint(sys.maxint+1)).eq(
            rlong.fromlong(sys.maxint+1))
        assert rlong.fromrarith_int(r_uint(2*sys.maxint+1)).eq(
            rlong.fromlong(2*sys.maxint+1))

    def test_add(self):
        x = 123456789123456789000000L
        y = 123858582373821923936744221L
        for i in [-1, 1]:
            for j in [-1, 1]:
                f1 = rlong.fromlong(x * i)
                f2 = rlong.fromlong(y * j)
                result = f1.add(f2)
                assert result.tolong() == x * i + y * j

    def test_sub(self):
        x = 12378959520302182384345L
        y = 88961284756491823819191823L
        for i in [-1, 1]:
            for j in [-1, 1]:
                f1 = rlong.fromlong(x * i)
                f2 = rlong.fromlong(y * j)
                result = f1.sub(f2)
                assert result.tolong() == x * i - y * j

    def test_subzz(self):
        w_l0 = rlong.fromint(0)
        assert w_l0.sub(w_l0).tolong() == 0

    def test_mul(self):
        x = -1238585838347L
        y = 585839391919233L
        f1 = rlong.fromlong(x)
        f2 = rlong.fromlong(y)
        result = f1.mul(f2)
        assert result.tolong() == x * y
        # also test a * a, it has special code
        result = f1.mul(f1)
        assert result.tolong() == x * x

    def test_tofloat(self):
        x = 12345678901234567890L ** 10
        f1 = rlong.fromlong(x)
        d = f1.tofloat()
        assert d == float(x)
        x = x ** 100
        f1 = rlong.fromlong(x)
        assert raises(OverflowError, f1.tofloat)

    def test_fromfloat(self):
        x = 1234567890.1234567890
        f1 = rlong.fromfloat(x)
        y = f1.tofloat()
        assert f1.tolong() == long(x)
        # check overflow
        #x = 12345.6789e10000000000000000000000000000
        # XXX don't use such consts. marshal doesn't handle them right.
        x = 12345.6789e200
        x *= x
        assert raises(OverflowError, rlong.fromfloat, x)

    def test_eq(self):
        x = 5858393919192332223L
        y = 585839391919233111223311112332L
        f1 = rlong.fromlong(x)
        f2 = rlong.fromlong(-x)
        f3 = rlong.fromlong(y)
        assert f1.eq(f1)
        assert f2.eq(f2)
        assert f3.eq(f3)
        assert not f1.eq(f2)
        assert not f1.eq(f3)

    def test_lt(self):
        val = [0, 0x111111111111, 0x111111111112, 0x111111111112FFFF]
        for x in gen_signs(val):
            for y in gen_signs(val):
                f1 = rlong.fromlong(x)
                f2 = rlong.fromlong(y)
                assert (x < y) ==  f1.lt(f2)

    def test_int_conversion(self):
        f1 = rlong.fromlong(12332)
        f2 = rlong.fromint(12332)
        assert f2.tolong() == f1.tolong()
        assert f2.toint()
        assert rlong.fromlong(42).tolong() == 42
        assert rlong.fromlong(-42).tolong() == -42

        u = f2.touint()
        assert u == 12332
        assert type(u) is r_uint

    def test_conversions(self):
        for v in (0, 1, -1, sys.maxint, -sys.maxint-1):
            assert rlong.fromlong(long(v)).tolong() == long(v)
            l = rlong.fromint(v)
            assert l.toint() == v
            if v >= 0:
                u = l.touint()
                assert u == v
                assert type(u) is r_uint
            else:
                py.test.raises(ValueError, l.touint)

        toobig_lv1 = rlong.fromlong(sys.maxint+1)
        assert toobig_lv1.tolong() == sys.maxint+1
        toobig_lv2 = rlong.fromlong(sys.maxint+2)
        assert toobig_lv2.tolong() == sys.maxint+2
        toobig_lv3 = rlong.fromlong(-sys.maxint-2)
        assert toobig_lv3.tolong() == -sys.maxint-2

        for lv in (toobig_lv1, toobig_lv2, toobig_lv3):
            py.test.raises(OverflowError, lv.toint)

        lmaxuint = rlong.fromlong(2*sys.maxint+1)
        toobig_lv4 = rlong.fromlong(2*sys.maxint+2)

        u = lmaxuint.touint()
        assert u == 2*sys.maxint+1

        py.test.raises(ValueError, toobig_lv3.touint)
        py.test.raises(OverflowError, toobig_lv4.touint)


    def test_pow_lll(self):
        x = 10L
        y = 2L
        z = 13L
        f1 = rlong.fromlong(x)
        f2 = rlong.fromlong(y)
        f3 = rlong.fromlong(z)
        v = f1.pow(f2, f3)
        assert v.tolong() == pow(x, y, z)
        f1, f2, f3 = [rlong.fromlong(i)
                      for i in (10L, -1L, 42L)]
        py.test.raises(TypeError, f1.pow, f2, f3)
        f1, f2, f3 = [rlong.fromlong(i)
                      for i in (10L, 5L, 0L)]
        py.test.raises(ValueError, f1.pow, f2, f3)

    def test_pow_lln(self):
        x = 10L
        y = 2L
        f1 = rlong.fromlong(x)
        f2 = rlong.fromlong(y)
        v = f1.pow(f2)
        assert v.tolong() == x ** y

    def test_normalize(self):
        f1 = rlong([1, 0], 1)
        f1._normalize()
        assert len(f1.digits) == 1
        f0 = rlong([0], 0)
        assert f1.sub(f1).eq(f0)

    def test_invert(self):
        x = 3 ** 40
        f1 = rlong.fromlong(x)
        f2 = rlong.fromlong(-x)
        r1 = f1.invert()
        r2 = f2.invert()
        assert r1.tolong() == -(x + 1)
        assert r2.tolong() == -(-x + 1)

    def test_shift(self):
        negative = rlong.fromlong(-23)
        big = rlong.fromlong(2L ** 100L)
        for x in gen_signs([3L ** 30L, 5L ** 20L, 7 ** 300, 0L, 1L]):
            f1 = rlong.fromlong(x)
            py.test.raises(ValueError, f1.lshift, negative)
            py.test.raises(ValueError, f1.rshift, negative)
            py.test.raises(OverflowError, f1.lshift, big)
            py.test.raises(OverflowError, f1.rshift, big)
            for y in [0L, 1L, 32L, 2304L, 11233L, 3 ** 9]:
                f2 = rlong.fromlong(y)
                res1 = f1.lshift(f2).tolong()
                res2 = f1.rshift(f2).tolong()
                assert res1 == x << y
                assert res2 == x >> y

class TestInternalFunctions(object):
    def test__inplace_divrem1(self):
        # signs are not handled in the helpers!
        x = 1238585838347L
        y = 3
        f1 = rlong.fromlong(x)
        f2 = y
        remainder = lobj._inplace_divrem1(f1, f1, f2)
        assert (f1.tolong(), remainder) == divmod(x, y)

    def test__divrem1(self):
        # signs are not handled in the helpers!
        x = 1238585838347L
        y = 3
        f1 = rlong.fromlong(x)
        f2 = y
        div, rem = lobj._divrem1(f1, f2)
        assert (div.tolong(), rem) == divmod(x, y)

    def test__muladd1(self):
        x = 1238585838347L
        y = 3
        z = 42
        f1 = rlong.fromlong(x)
        f2 = y
        f3 = z
        prod = lobj._muladd1(f1, f2, f3)
        assert prod.tolong() == x * y + z

    def test__x_divrem(self):
        x = 12345678901234567890L
        for i in range(100):
            y = long(randint(0, 1 << 30))
            y <<= 30
            y += randint(0, 1 << 30)
            f1 = rlong.fromlong(x)
            f2 = rlong.fromlong(y)
            div, rem = lobj._x_divrem(f1, f2)
            assert div.tolong(), rem.tolong() == divmod(x, y)

    def test__divrem(self):
        x = 12345678901234567890L
        for i in range(100):
            y = long(randint(0, 1 << 30))
            y <<= 30
            y += randint(0, 1 << 30)
            for sx, sy in (1, 1), (1, -1), (-1, -1), (-1, 1):
                sx *= x
                sy *= y
                f1 = rlong.fromlong(sx)
                f2 = rlong.fromlong(sy)
                div, rem = lobj._x_divrem(f1, f2)
                assert div.tolong(), rem.tolong() == divmod(sx, sy)

    # testing Karatsuba stuff
    def test__v_iadd(self):
        f1 = rlong([lobj.MASK] * 10, 1)
        f2 = rlong([1], 1)
        carry = lobj._v_iadd(f1.digits, 1, len(f1.digits)-1, f2.digits, 1)
        assert carry == 1
        assert f1.tolong() == lobj.MASK

    def test__v_isub(self):
        f1 = rlong([lobj.MASK] + [0] * 9 + [1], 1)
        f2 = rlong([1], 1)
        borrow = lobj._v_isub(f1.digits, 1, len(f1.digits)-1, f2.digits, 1)
        assert borrow == 0
        assert f1.tolong() == (1 << lobj.SHIFT) ** 10 - 1

    def test__kmul_split(self):
        split = 5
        diglo = [0] * split
        dighi = [lobj.MASK] * split
        f1 = rlong(diglo + dighi, 1)
        hi, lo = lobj._kmul_split(f1, split)
        assert lo.digits == [0]
        assert hi.digits == dighi

    def test__k_mul(self):
        digs= lobj.KARATSUBA_CUTOFF * 5
        f1 = rlong([lobj.MASK] * digs, 1)
        f2 = lobj._x_add(f1,rlong([1], 1))
        ret = lobj._k_mul(f1, f2)
        assert ret.tolong() == f1.tolong() * f2.tolong()

    def test__k_lopsided_mul(self):
        digs_a = lobj.KARATSUBA_CUTOFF + 3
        digs_b = 3 * digs_a
        f1 = rlong([lobj.MASK] * digs_a, 1)
        f2 = rlong([lobj.MASK] * digs_b, 1)
        ret = lobj._k_lopsided_mul(f1, f2)
        assert ret.tolong() == f1.tolong() * f2.tolong()




class TestTranslatable(object):

    def test_args_from_rarith_int(self):
        from pypy.rpython.test.test_llinterp import interpret
        def fn():
            return (rlong.fromrarith_int(0),
                    rlong.fromrarith_int(17),
                    rlong.fromrarith_int(-17),
                    rlong.fromrarith_int(r_uint(0)),
                    rlong.fromrarith_int(r_uint(17)))
        interpret(fn, [])
