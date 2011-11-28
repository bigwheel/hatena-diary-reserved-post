# -*- coding: utf-8 -*-

from google.appengine.dist import use_library
use_library('django', '1.2')
import datetime
from google.appengine.api import urlfetch
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

import oauth

from main import ReservedPost, UserProperty

class MainPage(webapp.RequestHandler):
    def get(self, mode=""):
        hatenaOauthClient = oauth.HatenaClient("bLgBYjM0mxzK7Q==", "BUDLSz9wMZgjJgxiFihI5uogoPQ=",
                                               None, scope = "read_public,write_public," +
                                               "read_private,write_private")

        pastTask = ReservedPost.gql("WHERE date <= DATETIME('%s')" % 
                             (datetime.datetime.now() + datetime.timedelta(hours=9))
                             .strftime(u"%Y-%m-%d %H:%M:%S"))
        for reservedPost in pastTask:
            userProperty = UserProperty.gql("WHERE g_username = :1",
                                            reservedPost.g_username).get()
            result = hatenaOauthClient.make_request(url=reservedPost.url, token=userProperty.accessToken,
                                         secret=userProperty.accessSecret, method=urlfetch.PUT,
                                         headers={"X-HATENA-PUBLISH":"1"})
            self.response.out.write(str(result.status_code) + "<br>")
            self.response.out.write(str(reservedPost.url) + "<br>")
            self.response.out.write(result.content)
            reservedPost.delete()
        
        return

application = webapp.WSGIApplication([('/(.*)', MainPage)], debug=True)


def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
