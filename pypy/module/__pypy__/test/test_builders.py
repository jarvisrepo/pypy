class AppTestBuilders(object):
    spaceconfig = dict(usemodules=['__pypy__'])

    def test_simple(self):
        from __pypy__.builders import StringBuilder
        b = StringBuilder()
        b.append("abc")
        b.append("123")
        b.append("1")
        s = b.build()
        assert s == "abc1231"
        assert type(s) is unicode
        assert b.build() == s
        b.append("123")
        assert b.build() == s + "123"
        assert type(b.build()) is unicode

    def test_preallocate(self):
        from __pypy__.builders import StringBuilder
        b = StringBuilder(10)
        b.append("abc")
        b.append("123")
        s = b.build()
        assert s == "abc123"
        assert type(s) is unicode

    def test_append_slice(self):
        from __pypy__.builders import StringBuilder
        b = StringBuilder()
        b.append_slice("abcdefgh", 2, 5)
        raises(ValueError, b.append_slice, "1", 2, 1)
        s = b.build()
        assert s == "cde"
        b.append_slice("abc", 1, 2)
        assert b.build() == "cdeb"

    def test_stringbuilder(self):
        from __pypy__.builders import BytesBuilder
        b = BytesBuilder()
        b.append(b"abc")
        b.append(b"123")
        assert len(b) == 6
        b.append(b"you and me")
        s = b.build()
        assert len(b) == 16
        assert s == b"abc123you and me"
        assert b.build() == s

    def test_encode(self):
        from __pypy__.builders import UnicodeBuilder
        b = UnicodeBuilder()
        raises(UnicodeDecodeError, b.append, b'\xc0')
