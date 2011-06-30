# -*- coding: utf-8 -*-

from google.appengine.dist import use_library
use_library('django', '1.2')
import os
import re
import datetime
from google.appengine.api import users
from google.appengine.api import urlfetch
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
import xml.etree.ElementTree as etree

import oauth

class UserProperty(db.Model):
    g_username = db.UserProperty()
    h_username = db.StringProperty()
    accessToken = db.StringProperty()
    accessSecret = db.StringProperty()

class ReservedPost(db.Model):
    g_username = db.UserProperty()
    date = db.DateTimeProperty()
    url = db.StringProperty()

class MainPage(webapp.RequestHandler):
    def get(self, mode=""):
        google_user_info = users.get_current_user()
        
        if not google_user_info:
            return self.redirect(users.create_login_url(self.request.uri))
        # TODO: 起動時に必ず出るエラーは、ここのreturn文が原因。文章を分解するべき？

        verify_url = "%s/verify" % self.request.host_url
        
        hatenaOauthClient = oauth.HatenaClient("bLgBYjM0mxzK7Q==", "BUDLSz9wMZgjJgxiFihI5uogoPQ=",
                                               verify_url, scope = "read_public,write_public," +
                                               "read_private,write_private")

        if mode == "": # トップページ
            path = os.path.join(os.path.dirname(__file__), 'index.html')
            return self.response.out.write(template.render(path, {}))
        elif mode == "login":
            return self.redirect(hatenaOauthClient.get_authorization_url())
        elif mode == "verify":
            auth_token = self.request.get("oauth_token")
            auth_verifier = self.request.get("oauth_verifier")
            try:
                user_info = hatenaOauthClient.get_user_info(auth_token, auth_verifier=auth_verifier)
            except:
                return self.redirect(verify_url) # エラー用のページを用意して、そのURLに移動するべき
            
            # すでにデータベースにあるなら上書きで更新。なければ新たにレコードを追加
            userPropertys = UserProperty.gql("WHERE g_username = :1", users.get_current_user())
            recordCount = userPropertys.count(3) # たぶん2でいいはずだが、自信がないので3にしておく
            if recordCount > 1:
                raise Exception, u"同じgoogleアカウントに紐付されたレコードが2つ以上あります。"
                # TODO: これは当然ながら発生しうる。例えば複数のはてなアカウントを管理しているなど
                # なので、やはり正式に運営するにはdjango+セッションIDである必要がある
            elif recordCount == 0: 
                userProperty = UserProperty() # レコードが一つもない場合、新たに作成
            else: # recordCount == 1
                userProperty = userPropertys.get() # 一つあればそれを引用して(下で)上書き(する)
            
            userProperty.g_username = users.get_current_user()
            userProperty.h_username = user_info["id"]
            userProperty.accessToken = user_info["token"]
            userProperty.accessSecret = user_info["secret"]
            userProperty.put()
            return self.redirect("%s/list" % self.request.host_url)
        elif mode == "list":
            userPropertys = UserProperty.gql("WHERE g_username = :1", users.get_current_user())
            recordCount = userPropertys.count(3) # たぶん2でいいはずだが、自信がないので3にしておく
            if recordCount == 0:
                self.redirect(verify_url)
            elif recordCount > 1:
                raise Exception, u"同じgoogleアカウントに紐付されたレコードが2つ以上あります。"
                # TODO: これは当然ながら発生しうる。例えば複数のはてなアカウントを管理しているなど
                # なので、やはり正式に運営するにはdjango+セッションIDである必要がある
            else: # recordCount == 1
                userProperty = userPropertys.get()
                url = "http://d.hatena.ne.jp/%s/atom/draft" % userProperty.h_username
                result = hatenaOauthClient.make_request(url=url, token=userProperty.accessToken,
                                             secret=userProperty.accessSecret, method=urlfetch.GET)
                
                dom = etree.fromstring(result.content)
                xmlns = "http://www.w3.org/2005/Atom" # XMLの名前空間
                entries = dom.findall("./{%s}entry" % xmlns)
                titleAndAtomLinkSetNodes = map((lambda entry:
                                                (entry.find("./{%s}title" % xmlns),
                                                 entry.find("./{%s}link" % xmlns))), entries)
                titleAndAtomLinkSets = map((lambda node: (node[0].text, node[1].get("href"))),
                                       titleAndAtomLinkSetNodes)
                
                titleAndAtomLinkAndLinkSets = map((lambda tAALSet: (tAALSet[0], tAALSet[1],
                    re.sub("/atom/draft/", "/draft?epoch=", tAALSet[1]))), titleAndAtomLinkSets)
                
                now = datetime.datetime.now()
                YMD = now.strftime(u"%Y-%m-%d")
                H = now.strftime(u"%H:")
                HM = H + ("%02d" % ((now.minute / 10) * 10))
                
                template_values = {"titleAndAtomLinkAndLinkSets":titleAndAtomLinkAndLinkSets,
                                   "YMD":YMD, "HM":HM}
                path = os.path.join(os.path.dirname(__file__), 'list.html')
                return self.response.out.write(template.render(path, template_values))
        elif mode == "confirm":
            if not self.request.get("article"):
                return self.redirect("%s/list" % self.request.host_url)
            YMD = self.request.get("date")
            HM = self.request.get("time")
            from time import strptime
            date = datetime.datetime(*strptime(YMD + HM, "%Y-%m-%d%H:%M")[0:5])
            reservedPost = ReservedPost()
            reservedPost.g_username = users.get_current_user()
            reservedPost.date = date
            reservedPost.url = self.request.get("article")
            reservedPost.put()
            
            return self.response.out.write("Store OK!")
        elif mode == "post":
            pastTask = ReservedPost.gql("WHERE date <= DATETIME('%s')" % 
                                 datetime.datetime.now().strftime(u"%Y-%m-%d %H:%M:%S"))
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
