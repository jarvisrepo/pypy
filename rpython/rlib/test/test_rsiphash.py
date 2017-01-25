from rpython.rlib.rsiphash import siphash24, choosen_seed
from rpython.rtyper.lltypesystem import rffi


CASES = [
    (2323638336262702335 , ""),
    (5150479602681463644 , "h"),
    (1013213613370725794 , "he"),
    (7028032310911240238 , "hel"),
    (9535960132410784494 , "hell"),
    (3256502711089771242 , "hello"),
    (2389188832234450176 , "hello "),
    (13253855839845990393, "hello w"),
    (7850036019043917323 , "hello wo"),
    (14283308628425005953, "hello wor"),
    (9605549962279590084 , "hello worl"),
    (16371281469632894235, "hello world"),
    (7298637955795769949 , "hello world\x9a"),
    (13530878135053370821, "hello world\xf3\x80"),
    (1643533543579802994 , "\xffhel\x82lo world\xbc"),
    (14632093238728197380, "hexlylxox rewqw"),
    (3434253029196696424 , "hexlylxox rewqws"),
    (9855754545877066788 , "hexlylxox rewqwsv"),
    (5233065012564472454 , "hexlylxox rewqwkashdw89"),
    (16768585622569081808, "hexlylxox rewqwkeashdw89"),
    (17430482483431293463, "HEEExlylxox rewqwkashdw89"),
    (695783005783737705  , "hello woadwealidewd 3829ez 32ig dxwaebderld"),
]

def check(s):
    p = rffi.str2charp(s)
    q = rffi.str2charp('?' + s)
    with choosen_seed(0x8a9f065a358479f4, 0x11cb1e9ee7f40e1f,
                      test_misaligned_path=True):
        x = siphash24(p, len(s))
        y = siphash24(rffi.ptradd(q, 1), len(s))
    rffi.free_charp(p)
    rffi.free_charp(q)
    assert x == y
    return x

def test_siphash24():
    for expected, string in CASES:
        assert check(string) == expected
