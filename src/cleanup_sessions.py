# -*- coding: utf-8 -*-

from gaesessions import delete_expired_sessions
while not delete_expired_sessions():
    pass

print "expired_sessions are deleted."