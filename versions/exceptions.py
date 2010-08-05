class VersionsException(Exception):
    pass

class VersionDoesNotExist(VersionsException):
    pass

class VersionsMultipleParents(VersionsException):
    pass

class VersionsManagementException(VersionsException):
    pass
