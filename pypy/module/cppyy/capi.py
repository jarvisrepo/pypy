import py, os

from pypy.translator.tool.cbuild import ExternalCompilationInfo
from pypy.rpython.lltypesystem import rffi, lltype

srcpath = py.path.local(__file__).dirpath().join("src")
incpath = py.path.local(__file__).dirpath().join("include")

if os.environ.get("ROOTSYS"):
    rootincpath = [os.path.join(os.environ["ROOTSYS"], "include")]
    rootlibpath = [os.path.join(os.environ["ROOTSYS"], "lib")]
else:
    rootincpath = []
    rootlibpath = []

eci = ExternalCompilationInfo(
    separate_module_files=[srcpath.join("reflexcwrapper.cxx")],
    include_dirs=[incpath] + rootincpath,
    includes=["reflexcwrapper.h"],
    library_dirs=rootlibpath,
    libraries=["Reflex"],
    use_cpp_linker=True,
)

c_cppyy_get_typehandle = rffi.llexternal(
    "cppyy_get_typehandle",
    [rffi.CCHARP], rffi.VOIDP,
    compilation_info=eci)

c_callstatic_l = rffi.llexternal(
    "callstatic_l",
    [rffi.VOIDP, rffi.INT, rffi.INT, rffi.VOIDPP], rffi.LONG,
    compilation_info=eci)
c_cppyy_construct = rffi.llexternal(
    "cppyy_construct",
    [rffi.VOIDP, rffi.INT, rffi.VOIDPP], rffi.VOIDP,
    compilation_info=eci)
c_cppyy_call_l = rffi.llexternal(
    "cppyy_call_l",
    [rffi.VOIDP, rffi.INT, rffi.VOIDP, rffi.INT, rffi.VOIDPP], rffi.LONG,
    compilation_info=eci)
c_cppyy_call_d = rffi.llexternal(
    "cppyy_call_d",
    [rffi.VOIDP, rffi.INT, rffi.VOIDP, rffi.INT, rffi.VOIDPP], rffi.DOUBLE,
    compilation_info=eci)
c_cppyy_destruct = rffi.llexternal(
    "cppyy_destruct",
    [rffi.VOIDP, rffi.VOIDP], lltype.Void,
    compilation_info=eci)


c_num_methods = rffi.llexternal(
    "num_methods",
    [rffi.VOIDP], rffi.INT,
    compilation_info=eci)
c_method_name = rffi.llexternal(
    "method_name",
    [rffi.VOIDP, rffi.INT], rffi.CCHARP,
    compilation_info=eci)
c_result_type_method = rffi.llexternal(
    "result_type_method",
    [rffi.VOIDP, rffi.INT], rffi.CCHARP,
    compilation_info=eci)
c_num_args_method = rffi.llexternal(
    "num_args_method",
    [rffi.VOIDP, rffi.INT], rffi.INT,
    compilation_info=eci)
c_arg_type_method = rffi.llexternal(
    "arg_type_method",
    [rffi.VOIDP, rffi.INT, rffi.INT], rffi.CCHARP,
    compilation_info=eci)
c_is_constructor = rffi.llexternal(
    "is_constructor",
    [rffi.VOIDP, rffi.INT], rffi.INT,
    compilation_info=eci)
c_is_static = rffi.llexternal(
    "is_static",
    [rffi.VOIDP, rffi.INT], rffi.INT,
    compilation_info=eci)
c_myfree = rffi.llexternal(
    "myfree",
    [rffi.VOIDP], lltype.Void,
    compilation_info=eci)

def charp2str_free(charp):
    string = rffi.charp2str(charp)
    c_myfree(charp)
    return string
