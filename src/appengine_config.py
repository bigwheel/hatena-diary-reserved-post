# -*- coding: utf-8 -*-

from gaesessions import SessionMiddleware

def webapp_add_wsgi_middleware(app):
    app = SessionMiddleware(app, cookie_key="8xGsf6jTyRjzzaBPL5EF33KWYiB5NkphJk7KxPMgdrfpf4cxsT")
    return app
