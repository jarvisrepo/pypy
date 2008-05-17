from pypy.rpython.lltypesystem import lltype, rffi
from pypy.rlib.rsdl import RSDL

def get_rgb(color, format):
    rgb = lltype.malloc(rffi.CArray(RSDL.Uint8), 3, flavor='raw')
    try:
        RSDL.GetRGB(color,
                    format,
                    rffi.ptradd(rgb, 0),
                    rffi.ptradd(rgb, 1),
                    rffi.ptradd(rgb, 2))
        r = rffi.cast(lltype.Signed, rgb[0])
        g = rffi.cast(lltype.Signed, rgb[1])
        b = rffi.cast(lltype.Signed, rgb[2])
        result = r, g, b
    finally:
        lltype.free(rgb, flavor='raw')

    return result

def get_rgba(color, format):
    rgb = lltype.malloc(rffi.CArray(RSDL.Uint8), 4, flavor='raw')
    try:
        RSDL.GetRGBA(color,
                    format,
                    rffi.ptradd(rgb, 0),
                    rffi.ptradd(rgb, 1),
                    rffi.ptradd(rgb, 2),
                    rffi.ptradd(rgb, 3))
        r = rffi.cast(lltype.Signed, rgb[0])
        g = rffi.cast(lltype.Signed, rgb[1])
        b = rffi.cast(lltype.Signed, rgb[2])
        a = rffi.cast(lltype.Signed, rgb[3])
        result = r, g, b, a
    finally:
        lltype.free(rgb, flavor='raw')

    return result

def get_pixel(image, x, y):
    """Return the pixel value at (x, y)
    NOTE: The surface must be locked before calling this!
    """
    bpp = rffi.getintfield(image.c_format, 'c_BytesPerPixel')
    pitch = rffi.getintfield(image, 'c_pitch')
    # Here p is the address to the pixel we want to retrieve
    p = rffi.ptradd(image.c_pixels, y * pitch + x * bpp)
    if bpp == 1:
        return rffi.cast(RSDL.Uint32, p[0])
    elif bpp == 2:
        p = rffi.cast(RSDL.Uint16P, p)
        return rffi.cast(RSDL.Uint32, p[0])
    elif bpp == 3:
        p0 = rffi.cast(lltype.Signed, p[0])
        p1 = rffi.cast(lltype.Signed, p[1])
        p2 = rffi.cast(lltype.Signed, p[2])
        if RSDL.BYTEORDER == RSDL.BIG_ENDIAN:
            result = p0 << 16 | p1 << 8 | p2
        else:
            result = p0 | p1 << 8 | p2 << 16
        return rffi.cast(RSDL.Uint32, result)
    elif bpp == 4:
        p = rffi.cast(RSDL.Uint32P, p)
        return p[0]
    else:
        raise ValueError("bad BytesPerPixel")
