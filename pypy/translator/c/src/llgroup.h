#ifndef _PYPY_LL_GROUP_H_
#define _PYPY_LL_GROUP_H_


#define GROUP_MEMBER_OFFSET(group, membername)  \
  ((unsigned short)((((char*)&membername) - ((char*)&group)) / sizeof(long)))

#define OP_GET_GROUP_MEMBER(groupptr, compactoffset, r)  \
  r = ((char*)groupptr) + ((long)compactoffset)*sizeof(long)

#define OP_GET_NEXT_GROUP_MEMBER(groupptr, compactoffset, skipoffset, r)  \
  r = ((char*)groupptr) + ((long)compactoffset)*sizeof(long) + skipoffset

#define OP_IS_GROUP_MEMBER_ZERO(compactoffset, r) \
  r = (compactoffset == 0)

/* A macro to crash at compile-time if sizeof(group) is too large.
   Uses a hack that I've found on some random forum.  Haaaaaaaaaackish. */
#define PYPY_GROUP_CHECK_SIZE(groupname)                              \
  typedef char group_##groupname##_is_too_large[2*(sizeof(groupname)  \
                                                   <= 65536 * sizeof(long))-1]


#endif /* _PYPY_LL_GROUP_H_ */
