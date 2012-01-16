# -*- coding: utf-8 -*-

from google.appengine.dist import use_library
use_library('django', '1.2')

# このファイルはconsumer_key_and_secret.pyのテンプレートです。
# 実際のサービスはこのファイルをconsumer_key_and_secret.pyにリネームし、
# 下の関数の返り値にそれぞれconsumer_keyおよびconsumer_secretを入力して実行されます

def getConsumerKey():
    return "こんしゅーまー・きー"

def getConsumerSecret():
    return "こんしゅーまー・しーくれっと"
