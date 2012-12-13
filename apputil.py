#!/usr/bin/python
# -*- coding: utf-8 -*-
import couchdbkit
import logging
import sys
import os

import urllib2
import urllib
import json
import base64
import re


class apputil(object):

    def __init__(
        self,
        app_id,
        app_key,
        logfile=sys.stdout,
        ):
        self.app_id = app_id
        self.app_key = app_key
        logging.basicConfig(format="%(levelname)s %(message)s", stream=logfile,
                            level=logging.DEBUG)
        self.log = logging.getLogger("example")
        self.streamdb_name = "streamdb_" + self.app_id + "_ext"
        couchdburl = os.getenv("COUCHDB_SERVER", "https://www.mosami.com/couch_ext")
        dummy = "REGEX_PROBLEM_BE_GONE"
        couchdburl = re.sub("(https?://)", r"\1" + dummy + app_id + ":" + app_key
                            + "@", couchdburl).replace(dummy, "")
        self.Server = couchdbkit.Server(couchdburl)
        self.db = self.Server.get_or_create_db(self.streamdb_name)

    def monitor_streams(self, callback=None, **kwargs):
        if callback == None:
            callback = self._default_callback
        consumer = couchdbkit.Consumer(self.db)
        try:
            while True:
                consumer.wait(callback, include_docs=True, heartbeat=100, **kwargs)
        except Exception, inst:
            self.log.error("issue watching database for changes:%s" % inst)
        self.log.critical("monitor_streams has failed, no longer tracking streams.")

    def _default_callback(self, change):
        self.log.info("changes callback:")
        if "doc" in change:
            self.log.info("changes doc:%s" % change["doc"])
        else:
            self.log.info("beep:%s" % change)

    # The following should work, but couchdbkit seems to have trouble with it, and all views on the external DB.
    # The solution is the less-than-graceful workaround below ...
#    def stream_names(self):
#        return [doc['doc']['name'] for doc in self.db.all_docs(include_docs=True).all() if 'doc' in doc and 'name' in doc['doc']]

    def stream_names(self):
        # urllib2 can't handle credentials embedded in the uri, so we'll have to get the uri back from the env var
        res = self._urlload(os.getenv("COUCHDB_SERVER",
                            "https://www.mosami.com/couch_ext") + "/"
                            + self.streamdb_name + "/_design/app/_view/name")
        return [doc["key"] for doc in res["rows"]]

    def _urlload(
        self,
        url,
        params={},
        method="GET",
        ):
        urllib2.ProxyHandler({})
        args = urllib.urlencode(params)
        if method == "GET":
            req = urllib2.Request(url + "?" + args)
        else:
            req = urllib2.Request(url, args)
        base64string = base64.encodestring("%s:%s" % (self.app_id,
                self.app_key))[:-1]
        req.add_header("Authorization", "Basic %s" % base64string)
        opener = urllib2.build_opener()
        try:
            f = opener.open(req, timeout=25)
            res = json.load(f)
        except Exception, inst:
            self.log.error("urlload error: %s" % inst)
            res = {}
            raise Exception
        return res


