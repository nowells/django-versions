import unittest

from versions.tests import testcases

def suite():
    s = unittest.TestSuite()
    s.addTest(unittest.defaultTestLoader.loadTestsFromModule(testcases))
    return s
