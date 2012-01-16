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

from password import consumer_key_and_secret

class UserProperty(db.Model):
    g_username = db.UserProperty()
    h_username = db.StringProperty()
    accessToken = db.StringProperty()
    accessSecret = db.StringProperty()

class ReservedPost(db.Model):
    g_username = db.UserProperty()
    date = db.DateTimeProperty()
    url = db.StringProperty()

def render_template(response, template_filename, template_dict, debug=False):
    path = os.path.join(os.path.dirname(__file__), "templates/" + template_filename)
    response.out.write(template.render(path, template_dict, debug))

class MainPage(webapp.RequestHandler):
    def get(self, mode=""):
        # まず最初にgoogleのログインを確認
        if not users.get_current_user():
            render_template(self.response, "require_google_login.html",
                            {"login_url":users.create_login_url(self.request.uri)})
            return

        verify_url = "%s/verify" % self.request.host_url
        hatenaOauthClient = oauth.HatenaClient(consumer_key_and_secret.getConsumerKey(),
                                               consumer_key_and_secret.getConsumerSecret(),
                                               verify_url, scope = "read_public,write_public," +
                                               "read_private,write_private")

        # 次にそのgoogleアカウントではてな日記のOauthがすでに認証されているか確認
        userPropertys = UserProperty.gql("WHERE g_username = :1", users.get_current_user())
        recordCount = userPropertys.count(2)
        if recordCount > 1:
            raise Exception, u"同じgoogleアカウントに紐付されたレコードが2つ以上あります。"
            # TODO: これは当然ながら発生しうる。例えば複数のはてなアカウントを管理しているなど
            # なので、やはり正式に運営するにはdjango+セッションIDである必要がある
        elif recordCount == 0: # そのgoogleアカウントではてなOauthが認証されていないなら
            auth_token = self.request.get("oauth_token", None)
            auth_verifier = self.request.get("oauth_verifier", None)
            # もしoauth認証を通った後でなければ
            if auth_token == None or auth_verifier == None:
                return render_template(self.response, "require_hatena_oauth.html",
                                {"auth_url":hatenaOauthClient.get_authorization_url()})
            try:
                user_info = hatenaOauthClient.get_user_info(auth_token, auth_verifier=auth_verifier)
            except:
                return self.response.out.write("Oauthのtokenおよびverifilerが正しくありません。")

            userProperty = UserProperty()
            userProperty.g_username = users.get_current_user()
            userProperty.h_username = user_info["id"]
            userProperty.accessToken = user_info["token"]
            userProperty.accessSecret = user_info["secret"]
            userProperty.put()
            return self.redirect(self.request.host_url)
        else: # recordCount == 1
            userProperty = userPropertys.get() # 一つあればそれを引用して(下で)上書き(する)

            # この時点でgoogleアカウントに紐付されてることと、
            # hatenaへのoauth認証が済んでいること(つまりuserPropertyに正しく入力されてること)が保証されてる

            if mode == "":
                message = "" # とりあえずメッセージを空にしておく
                typeOfAction = self.request.get("type_of_action")
                if typeOfAction == "":
                    pass
                elif typeOfAction == "reserve":
                    reservedPosts = ReservedPost.gql("WHERE url = :1", self.request.get("article_url"))
                    if reservedPosts.count(1) != 0:
                        message = "その記事はすでに予約されています"
                    else:
                        YMD = self.request.get("date")
                        HM = self.request.get("time")
                        from time import strptime
                        date = datetime.datetime(*strptime(YMD + HM, "%Y-%m-%d%H:%M")[0:5])
                        reservedPost = ReservedPost()
                        reservedPost.g_username = users.get_current_user()
                        reservedPost.date = date
                        reservedPost.url = self.request.get("article_url")
                        reservedPost.put()
                        message = "予約を追加しました"
                elif typeOfAction == "cancel":
                    reservedPosts = ReservedPost.gql("WHERE url = :1", self.request.get("article_url"))
                    reservedPostsNumber = reservedPosts.count(2)
                    if reservedPostsNumber == 2:
                        raise Exception, ("予約データベースの中に同じ記事のための予約が2つあります"
                                          + "(内部状態の異常)")
                    elif reservedPostsNumber == 0:
                        message = "そのような記事の予約は存在しません"
                    else: # reservedPostsNumber == 1
                        reservedPosts.get().delete()
                        message = "予約をキャンセルしました"
                elif typeOfAction == "delete_token":
                    self.deleteUserPropertyAndReservedPost(userProperty)
                    return self.redirect(self.request.host_url)
                else:
                    raise Exception, "未知のtype_of_action get変数が指定されてます"

                result = hatenaOauthClient.make_request(url="http://d.hatena.ne.jp/%s/atom/draft"
                                    % userProperty.h_username, token=userProperty.accessToken,
                                    secret=userProperty.accessSecret, method=urlfetch.GET)
        
                try:
                    titleAndAtomLinkAndLinkSets = self._palseDraftXml(result)
                except:
                    if result.content == "oauth_problem=token_revoked" or\
                                    result.content == "oauth_problem=token_rejected":
                        self.deleteUserPropertyAndReservedPost(userProperty)
                        return render_template(self.response, "token_error.html",
                                               {"message":result.content})
                    return render_template(self.response, "error_happened.html",
                                           {"message":result.content})
                
                reservedPostsForThisUser = ReservedPost.gql("WHERE g_username = :1",
                                                            users.get_current_user())
                
                nonReservedArticles = []
                reservedArticles = []
                
                for article in titleAndAtomLinkAndLinkSets:
                    for reservedPost in reservedPostsForThisUser:
                        if article[1] == reservedPost.url:
                            reservedArticles.append((article[0], article[1], article[2],
                                                     reservedPost.date))
                            break
                    else: # このelseはifに対応したelseではなく同インデントのforに対応するelseであることに注意
                        nonReservedArticles.append(article)
                
                (YMD, HM) = self._getYMDandHM()
                
                template_values = {"h_username":userProperty.h_username, "message":message,
                                   "reservedArticles":reservedArticles,
                                   "nonReservedArticles":nonReservedArticles, "YMD":YMD, "HM":HM}
                return render_template(self.response, "list_draft_articles.html", template_values)
            else:
                raise Exception, u"知らないモード(URL)です。" + mode

    def deleteUserPropertyAndReservedPost(self, userProperty):
        for reservedPost in ReservedPost.gql("WHERE g_username = :1", users.get_current_user()):
            reservedPost.delete()
        userProperty.delete()

    def _getYMDandHM(self):
        now = datetime.datetime.now() + datetime.timedelta(hours=9, minutes=10)
        # 日本とGMTの時差+9時間分と、最初の表示が現在時刻では面倒なので一応10分足しておく
        YMD = now.strftime(u"%Y-%m-%d")
        H = now.strftime(u"%H:")
        HM = H + ("%02d" % ((now.minute / 10) * 10))
        return (YMD, HM)
    
    def _palseDraftXml(self, xml):
        dom = etree.fromstring(xml.content)
        xmlns = "http://www.w3.org/2005/Atom" # XMLの名前空間
        entries = dom.findall("./{%s}entry" % xmlns)
        titleAndAtomLinkSetNodes = map((lambda entry:
                                        (entry.find("./{%s}title" % xmlns),
                                         entry.find("./{%s}link" % xmlns))), entries)
        titleAndAtomLinkSets = map((lambda node: (node[0].text, node[1].get("href"))),
                               titleAndAtomLinkSetNodes)
        
        return map((lambda tAALSet: (tAALSet[0], tAALSet[1],
            re.sub("/atom/draft/", "/draft?epoch=", tAALSet[1]))), titleAndAtomLinkSets)


application = webapp.WSGIApplication([('/(.*)', MainPage)], debug=True)


def main():
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
