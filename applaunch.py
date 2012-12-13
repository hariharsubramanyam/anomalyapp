#!/usr/bin/python
# -*- coding: utf-8 -*-
import logging
from pyramid.config import Configurator
from pyramid.view import view_config
from paste.httpserver import serve
from pyramid.response import Response
import sys
import os
import random
import time
import base64
import argparse
import ApplaunchClass
import urlparse
import glob
import uuid
import apputil
import thread
from signal import signal, SIGTERM
import atexit

from moutil import Mo


class ClientInterface(object):

    def __init__(
        self,
        log,
        port=8760,
        app_class=[],
        launch_params={},
        init_params={},
        app_id=0,
        app_key=0,
        ):
        self.log = log
        self.port = port
        self.apps = {}
        self.app_handles = {}
        self.init_results = {}
        self.app_class = app_class
        self.launch_params = launch_params
        self.init_params = init_params
        self.app_utils = ApplaunchClass.ApplaunchClass(self.log)
        self.queue = {}
        self.app_id = app_id
        self.app_key = app_key
        self.app = ""
        thread.start_new_thread(self.stream_listener, ())
        signal(SIGTERM, lambda signum, stack_frame: exit(1))
        atexit.register(self.shutdown)

    def stream_listener(self):
        if not self.app:
            self.app = apputil.apputil(self.app_id, self.app_key)
        self.app.monitor_streams(self.stream_notification)

    def stream_notification(self, change):
        if "doc" in change and "name" in change["doc"] and change["doc"]["name"] \
            in self.queue:
            if "_deleted" not in change["doc"] or not change["doc"]["_deleted"]:
                results = []
                for request in self.queue[change["doc"]["name"]]:
                    self.log.info("executing request:%s\n" % request)
                    (result, status) = self.app_command(request["args"])
                    self.log.info(("%s"
                                  % status if status else "<no status returned>"))
                    self.log.info(("%s"
                                  % result if result else "<no result returned>"))
            del self.queue[change["doc"]["name"]]

    def _process_request(self, request):
        if request.method == "POST":
            args = request.POST.mixed()
        elif request.method == "PUT":
            args = request.params.mixed()
        elif request.method == "GET":
            args = request.GET.mixed()
        elif request.method == "DELETE":
            args = request.params.mixed()
        else:
            args = {}

        if request.matchdict != None:
            matchdict = request.matchdict
        else:
            matchdict = {}

        args.update(matchdict)

        args["_remote_addr"] = request.remote_addr
        args["_path"] = request.path
        args["_host"] = request.host
        # we call 'module' args in jlaunch
        if "module" in args:
            args["pl"] = args["module"]

        return (request.method, args)

    def _get_json_args(self, request):
        return (request.POST.mixed() if request.method == "POST"
                 else (request.GET.mixed() if request.method == "GET" else {}))

    def create_app(self, args):
        launch_time = int(time.time() * 1000)
        if "appId" in args:
            if args["appId"] in self.apps:
                return ({"status": "error",
                        "error": "App %s already exists, cannot create."
                        % args["appId"]}, "409 Conflict")
            appId = args["appId"]
        else:
            appId = "app" + "%0*d" % (5, int(random.random() * 100000))
            while appId in self.apps:
                appId = "app" + "%0*d" % (5, int(random.random() * 100000))
        if self.app_class:
            # OBSOLETE PATH?
            self.apps[appId] = self.app_class(log=self.log,
                    launch_params=self.launch_params)
            if self.init_params:
                self.app.command("init", self.init_params)
            self.init_results[appId] = self.apps[appId].command("init",
                    self.init_params)
        else:
            if "app" not in args:
                return ({"status": "error", "error": "No app given."},
                        "400 Bad Request")
            else:
                if args["app"] not in self.app_handles:
                    self.log.info("importing %s" % args["app"])
                    try:
                        self.app_handles[args["app"]] = __import__(args["app"])
                    except Exception, inst:
                        self.log.critical("Import error:%s" % inst)
                        return ({
                            "status": "error",
                            "appId": appId,
                            "uri": "/apps/%s" % appId,
                            "error": "%s" % inst,
                            }, "400 Bad Request")
                full_params = self.launch_params
                full_params.update(args)
                full_params["app-starttime"] = launch_time
                print "launch_time:%s" % full_params
                self.apps[appId] = getattr(self.app_handles[args["app"]], args["app"
                        ])(log=self.log, app_id=self.app_id, app_key=self.app_key,
                           launch_params=full_params)
                init_result = self.apps[appId].command("init", **args)
                if type(init_result) == dict:
                    init_result.update(full_params)
                    self.init_results[appId] = init_result
                else:
                    self.init_results[appId] = {"init_result": init_result}
                    self.init_results[appId].update(full_params)

        return ({
            "status": "success",
            "appId": appId,
            "init": self.init_results[appId],
            "uri": "/apps/%s" % appId,
            }, "201 Created")

    def add_client_streams(self, request):
        # def add_client_streams(self, src_count, dst_count, **kwargs):
        request.response.headerlist.append(("Access-Control-Allow-Origin", "*"))
        request.response.headerlist.append(("Cache-Control", "no-cache"))

        (method, args) = self._process_request(request)

        (args, auth) = self._authorize(request, args)
        if not auth:
            self.log.info("Unauthorized request!")
            return self._unauth_response()

        rest_method = (args["_method"] if "_method" in args else request.method)

        if rest_method in ["POST", "PUT"]:
            # launch app
            (result, request.response.status) = self.add_streams(args)
            return result
        elif rest_method in ["DELETE"]:
            # delete everything
            (result, request.response.status) = self.del_streams(args)
            return result
        elif rest_method in ["GET"]:
            # Get a list of running apps
            request.response.status = "200 OK"
            return {"status": "success", "apps": self.apps(), "uri": "/apps"}

    def add_streams(self, args):
        if "block" not in args or self.stream_already_available(args["block"]):
            return self.app_command(args)
        else:
            if args["block"] not in self.queue:
                self.queue[args["block"]] = []
            self.queue[args["block"]].append({"args": args,
                    "timestamp": time.time()})
            return ({"status": "queued"}, "200 OK")

    def stream_already_available(self, stream_name):
        if not self.app:
            self.app = apputil.apputil(self.app_id)
        return stream_name in self.app.stream_names()

    def create_client_uri(self, args):
        if "client_uri" not in args:
            return ""
        else:
            return self.get_client_uri(args)

    def app_command(self, args):
        if "appId" not in args:
            return ({"status": "error", "error": "appId not given"},
                    "400 Bad Request")
        if "command" not in args:
            return ({"status": "error", "error": "command parameter must be given",
                    "appId": args["appId"]}, "400 Bad Request")
        if args["appId"] not in self.apps:
            return ({"status": "error", "error": "appId doesn't exist",
                    "appId": args["appId"]}, "400 Bad Request")
        return (self.apps[args["appId"]].command(args["command"], **args), "200 OK")

    # _authorize
    # We don't actually _authorize against 3scale here, because that requires giving out our private
    # provider ID key.  Instead, We prepare the arguments for the Mosami API call which will _authorize,
    # and reject the call if no developer key is given.
    def _authorize(self, request, args):
        if "app_id" in args and "app_key" in args:
            return (args, True)
        if app_id and app_key:
            args["app_id"] = app_id
            args["app_key"] = app_key
            return (args, app_key)
        if "Authorization" in request.headers:
            try:
                (args["app_id"], args["app_key"]) = \
                    base64.decodestring(request.authorization[1]).split(":", 2)
            except Exception, inst:
                self.log.error("[%s] - Invalid authorization header: %s" % (inst,
                               request.headers["Authorization"]))
            return (args, True)
        return (args, False)

    def _unauth_response(self):
        return Response("You are not _authorized to access this API",
                        status="401 Un_authorized")

    def url_apps(self, request):
        request.response.headerlist.append(("Access-Control-Allow-Origin", "*"))
        request.response.headerlist.append(("Cache-Control", "no-cache"))

        (method, args) = self._process_request(request)

        (args, auth) = self._authorize(request, args)
        if not auth:
            self.log.info("Unauthorized request!")
            print "Unauthorized request!"
            return self._unauth_response()

        rest_method = (args["_method"] if "_method" in args else request.method)

        if rest_method in ["POST", "PUT"]:
            # launch app
            (result, request.response.status) = self.create_app(args)
            return result
        elif rest_method in ["DELETE"]:
            # delete everything
            self.shutdown()
            request.response.status = "200 OK"
            return {"status": "success", "uri": "/apps"}
        elif rest_method in ["GET"]:
            # Get a list of running apps
            request.response.status = "200 OK"
            return {"status": "success", "apps": self.apps.keys(), "uri": "/apps"}

    def apps_appId(self, request):
        request.response.headerlist.append(("Access-Control-Allow-Origin", "*"))
        request.response.headerlist.append(("Cache-Control", "no-cache"))

        (method, args) = self._process_request(request)

        rest_method = (args["_method"] if "_method" in args else request.method)

        if args["appId"] not in self.apps:
            request.response.status = "404 Not Found"
            return {"status": "error", "error": "appId does not exist",
                    "appId": args["appId"]}

        if rest_method in ["POST", "PUT"]:
            (result, request.response.status) = self.app_command(args)
            return result
        elif rest_method in ["DELETE"]:
            self.apps[args["appId"]].shutdown()
            del self.apps[args["appId"]]
            request.response.status = "200 OK"
            return {"status": "success", "uri": "/apps/" + args["appId"]}
        elif rest_method in ["GET"]:
            args["command"] = "GET"
            # get result from app
            (result, request.response.status) = self.app_command(args)
            # add queued results
            result["queue"] = []
            for requests in self.queue.values():
                for request in requests:
                    if "args" in request and "appId" in request["args"] \
                        and request["args"]["appId"] == args["appId"]:
                        result["queue"].append(request)

#            get = {}
#            for appId in self.apps.keys():
#                get[appId] = []
#            for requests in self.queue.values():
#                for request in requests:
#                    if 'args' in request and 'appId' in request['args'] and request['args']['appId'] in get:
#                        get[request['args']['appId']].append(request)
#            return {'status':'success','apps':get,'uri':'/apps'}

            return result

    def available(self, request):
        request.response.headerlist.append(("Access-Control-Allow-Origin", "*"))
        request.response.headerlist.append(("Cache-Control", "no-cache"))

        (method, args) = self._process_request(request)

        rest_method = (args["_method"] if "_method" in args else request.method)

        if rest_method in ["POST", "PUT", "DELETE"]:
            request.response.status = "400 Bad Request"
            return {"status": "error", "error": "%s not supported.  Try GET." \
                    % rest_method, "uri": "/apps/available"}
        elif rest_method in ["GET"]:
            request.response.status = "200 OK"
            files = glob.glob("[A-Z]*.py")
            for remove in ["Recordings.py", "Recordings2.py", "ApplaunchClass.py",
                           "RecordingsVertical.py"]:
                files.remove(remove)
            for add in [
                "swipe",
                "convdir_position",
                "convdir_alpha",
                "facetrackzoom",
                "faceparallax",
                "nearfar",
                "pixelate",
                "focus",
                "mixer",
                "repub",
                "pointing",
                "anomalyApp"
                ]:
                files.append(add)
            return {"status": "success", "apps": files}

    def names(self, request):
        request.response.headerlist.append(("Access-Control-Allow-Origin", "*"))
        request.response.headerlist.append(("Cache-Control", "no-cache"))

        (method, args) = self._process_request(request)

        rest_method = (args["_method"] if "_method" in args else request.method)

        if rest_method in ["POST", "PUT", "DELETE"]:
            request.response.status = "400 Bad Request"
            return {"status": "error", "error": "%s not supported.  Try GET." \
                    % rest_method, "uri": "/apps/available"}
        elif rest_method in ["GET"]:
            request.response.status = "200 OK"
            count = int((args["count"] if "count" in args else (args["n"] if "n"
                        in args else 1)))
            names = [str(uuid.uuid4()) for dummy in range(0, count)]
            return {"status": "success", "uri": "/apps/names", "names": names}

    def shutdown(self, request={}):
        for app in self.apps.values():
            app.shutdown()
        self.apps = {}

    # shut down applaunch itself
    def terminate(self, request={}):
#        self.shutdown(request)
        os._exit(1)

    def ping(self, request={}):
        request.response.headerlist.append(("Access-Control-Allow-Origin", "*"))
        request.response.headerlist.append(("Cache-Control", "no-cache"))
        return {"status": "success", "ping": "pong"}

    def takeOver(self):
        config = Configurator(settings={"reload_all": True, "debug_all": False})

        config.add_route("apps", "/apps")
        config.add_view(self.url_apps, route_name="apps", renderer="json")

        config.add_route("available", "/apps/available")
        config.add_view(self.available, route_name="available", renderer="json")

        config.add_route("apps_appId", "/apps/{appId}")
        config.add_view(self.apps_appId, route_name="apps_appId", renderer="json")

        config.add_route("add_client_streams", "/apps/{appId}/streams")
        config.add_view(self.add_client_streams, route_name="add_client_streams",
                        renderer="json")

        config.add_route("names", "/names")
        config.add_view(self.names, route_name="names", renderer="json")

        config.add_route("terminate", "/terminate")
        config.add_view(self.terminate, route_name="terminate", renderer="json")

        config.add_route("ping", "/ping")
        config.add_view(self.ping, route_name="ping", renderer="json")

        config.add_route("slash", "/")
        config.add_view(self.ping, route_name="slash", renderer="json")

        # Serve the REST interface forever.
        app = config.make_wsgi_app()
        try:
            server = serve(app, host="0.0.0.0", port=self.port, start_loop=False)
            self.log.info("serving on %s" % self.port)
            server.serve_forever()
        except KeyboardInterrupt:
            self.log.info("Web Server Exit")
            raise


if __name__ == "__main__":
    logging.basicConfig(format="%(levelname)s %(message)s", stream=sys.stdout,
                        level=logging.DEBUG)
    log = logging.getLogger("mosami")

    parser = \
        argparse.ArgumentParser(description="Run Mosami server-side applications.")
    parser.add_argument("-i", "--app_id", type=str, help="developer key app_id",
                        default=os.getenv("MO_APP_ID"))
    parser.add_argument("-k", "--app_key", type=str, help="developer key app_key",
                        default=os.getenv("MO_APP_KEY"))
    parser.add_argument("-p", "--port", default=8768,
                        help="port applaunch should listen on; clients need to use "
                        "this port")
    args = vars(parser.parse_args())

    app_id = args["app_id"]
    app_key = args["app_key"]
    if not app_id or not app_key:
        print "The app_id and/or app_key are missing.  Fix by:"
        print "\tsetting MO_APP_ID and MO_APP_KEY environmental variables"
        print "or type:"
        print "\t$ python applaunch -h"
        print "for more options."
    else:
        try:
            intf = ClientInterface(log=log, port=args["port"], app_id=app_id,
                                   app_key=app_key)
            intf.takeOver()
        except (KeyboardInterrupt, SystemExit):
            log.info("^C received, shutting down")
        except Exception, inst:
            log.error("Exception : %s", inst)
            log.info("Terminating pipelines..")

