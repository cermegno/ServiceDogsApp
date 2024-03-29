import os
import unittest
import pytest
from controller import *
from model import *

class MyTestCase(unittest.TestCase):

#    def setUp(self):
#        model.app.testing = True
#        self.app = model.app.test_client()
#    def tearDown(self):
#        pass

    def test_getUser(self):
        createUser("tim", "password", "email", "1234", "admin", "email")
        user = getUser("tim")
        self.assertIn("password", user['password'])
        deleteUser("tim")


    def test_getRole(self):
        createUser("tim", "password", "email", "1234", "admin", "email")
        role = getRole("tim")
        self.assertIn("admin", role)
        deleteUser("tim")

    def test_getNotification(self):
        createUser("tim", "password", "email", "1234", "admin", "email")
        notification = getNotification("tim")
        self.assertIn(notification, "email")
        deleteUser("tim")

if __name__ == '__main__':
    unittest.main()


# Method	Equivalent to
# .assertEqual(a, b)	a == b
# .assertTrue(x)	bool(x) is True
# .assertFalse(x)	bool(x) is False
# .assertIs(a, b)	a is b
# .assertIsNone(x)	x is None
# .assertIn(a, b)	a in b
# .assertIsInstance(a, b)	isinstance(a, b)
# .assertIs(), .assertIsNone(), .assertIn(), and .assertIsInstance() all have opposite methods, named .assertIsNot(), and so forth.
