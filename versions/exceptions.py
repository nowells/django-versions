class VersionsException(Exception):
    pass

class VersionDoesNotExist(VersionsException):
    pass

class VersionsMultipleParents(VersionsException):
    pass
