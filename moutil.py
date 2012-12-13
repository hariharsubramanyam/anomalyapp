#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
moutil.py

Python bindings for Mosami API v0.1

The python-mosami package simplifies access to the Mosami API by providing:

- Developer application id and key management
- Pipeline launching and pipeline-id management
- Pipeline messaging support
- Pipeline and stream monitoring.
- Shutdown of pipelines

A single class, `Mo()` is used for a connection to a Mosami server,
simply instantiate `Mo()` with your app_id and app_key and you can start launching pipelines.

Using methods in `Mo()` such as jlaunch, you can launch pipelines and will be returned a MoLaunch() instance
to the launched pipeline you can use for further pipeline manipulations, for example: adding an input to a mixer pipeline.

A user callback can be setup when a pipeline is launched using `Mo().jlaunch()` that will be called
when messages are recieved for that pipeline, for example facetracker coordinates from an analyzer.

Quick example: start a mixer and add 'Stream1' test stream:

.. code-block:: python

    from moutil import Mo

    # Instantiate Mo() class
    mo = Mo(app_id='12345678', app_key='abcdefghijklmnop')
    # launch a mixer
    mixer = mo.jlaunch('cclMix', dst='output-mix')
    # add 'Stream1' to the mixer
    mixer.msg('add', stream='Stream1', mosaic=True)


And to terminate the mixer when your done:

.. code-block:: python

    mo.Shutdown()

"""

import time
import logging
import stomp
import json
import urllib
import urllib2
import os

# default mosami api server url - MO_SERVER environment variable overrides this, mo_server in class instantiation overrides that
# Use this server for external alu testing
MO_SERVER = "https://www.mosami.com/api"
# Use this server for internal alu testing
# MO_SERVER = 'http://mosami010.research.bell-labs.com/sapi'
# MO_SERVER = 'https://mosami.research.bell-labs.com/api'

MO_APP_ID = "app_id_not_given"
MO_APP_KEY = "app_key_not_given"


class Mo(object):

    """ 
    Main class instance to hold app id/key, pipelines launched, messages, etc 

    :param app_id: YOUR APPLICATION ID for authorization (required). Default: ``None``
    :param app_key: YOUR APPLICATION KEY for authorization (required).   Default: ``None``
    :param mo_server: Mosami API server.  Default: ``http://ppc.mosami.com/sapi``
    :param rx_msg_callback: Master callback function (optional) to be used for all  pipeline callbacks.  Default: ``None`` (no callback)
    :param block_on_launch: Block until pipeline is launched.  Default: ``True``
    :param block_on_state: Block until pipeline is active (or fails during launch).  Default: ``True``
    :param rtmp_output: Enable RTMP output for pipelines by default.  Default: ``True``

    """

    def __init__(
        self,
        app_id=None,
        app_key=None,
        mo_server=None,
        block_on_launch=True,
        block_on_state=True,
        rtmp_output=True,
        rx_msg_callback=None,
        ):

        # set defaults - priority: (1) Mo() (2) Environment (3) local file setting
        self.mo_server = self._envdefault(mo_server, "MO_SERVER", MO_SERVER)
        self.app_id = self._envdefault(app_id, "MO_APP_ID", MO_APP_ID)
        self.app_key = self._envdefault(app_key, "MO_APP_KEY", MO_APP_KEY)

        self.log = logging.getLogger()

        pylog = logging.getLogger("stomp.py")
        pylog.setLevel(logging.INFO)

        self.msg_connections = {}
        self.pipelines = {}
        self.user_global_msg_callback = rx_msg_callback
        self.block_on_launch = block_on_launch
        self.block_on_state = block_on_state
        self.rtmp_output = rtmp_output

    def _envdefault(
        self,
        inst_setting,
        env_default,
        default,
        ):
        if inst_setting != None:
            return inst_setting
        else:
            if env_default in os.environ:
                return os.environ[env_default]
            else:
                return default

    def watch_stream(self, stream_name, stream_msg_callback):
        """Monitor a stream for messages (from clients viewing the stream, stream events, statistics)
        
        :param stream_name: name of stream to monitor for messages
        :param stream_msg_callback: callback that should be called for stream messages
        
        """

        self.stream_msg_callback = stream_msg_callback
        topic = "%s.%s.stream" % (self.app_id, stream_name)
        for stompserver in self.msg_connections:
            self.msg_connections[stompserver].subscribe_generic(topic)

    def unwatch_stream(self, stream_name):
        topic = "%s.%s.stream" % (self.app_id, stream_name)
        for stompserver in self.msg_connections:
            self.msg_connections[stompserver].unsubscribe_generic(topic)

    def _master_rx_msg_callback(self, headers, message):
        # All messages from all pipelines come through this single callback
        # if the user wishes to have specific callbacks for a pipeline they are routed by this function
        # alternatively, the user can supply a single callback in Mo setup and do their own filtering
        try:
            msg = json.loads(message)
        except:
            self.log.error("Cannot JSON deserialize: %s" % str(message))
            return
        if headers["destination"].endswith(".stream"):
            if self.stream_msg_callback:
                self.stream_msg_callback(headers, msg)
        if "element" in msg:
            # suppress 'system' messages
            if msg["element"].startswith("mosrc") or msg["element"
                    ].startswith("mosink"):
                return
        try:
            pipelineid = headers["destination"].split("/")[2].split(".")[1]
        except:
            self.log.warning("Spurious message received from : %s"
                             % headers["destination"])
            return

        # call user-defined pipeline state update callback if required
        if "command" in msg:
            if msg["command"] == "state":
                if pipelineid in self.pipelines:
                    for pipeline in self.pipelines[pipelineid]:
                        pipeline.state = msg["state"]
                        if "message" in msg:
                            pipeline.last_state_message = msg["message"]
                        if pipeline.pipeline_state_callback:
                            pipeline.pipeline_state_callback(msg["state"])
        # if 'moMessageType' is not in msg, do not forward to the user callbacks
        # if 'moMessageType' not in msg:
        #    return

        # Service global user callback if required
        if self.user_global_msg_callback:
            if pipelineid in self.pipelines:
                pipeline_inst = self.pipelines[pipelineid][0]
            else:
                pipeline_inst = None
            self.user_global_msg_callback(pipeline_inst, msg, pipelineid)

        # Service individual user callbacks
        if pipelineid in self.pipelines:
            for pipeline in self.pipelines[pipelineid]:
                if pipeline.rx_msg_callback:
                    if pipeline.user_params:
                        pipeline.rx_msg_callback(msg,
                                user_params=pipeline.user_params)
                    else:
                        pipeline.rx_msg_callback(msg)

    def jlaunch(
        self,
        pipeline_name,
        rx_msg_callback=None,
        user_params=None,
        pipeline_state_callback=None,
        timeout=25,
        **kwargs
        ):
        """Launch a Mosami Pipeline
        
        :param pipeline_name: Name of molaunch API pipeline to launch
        :param rx_msg_callback: Callback to be called for received messages from pipeline.  Default ``None``
        :param user_params: Optional parameters that can be returned via the rx_msg_callback.  Default ``None``
        :param pipeline_state_callback: Callback to monitor pipeline state.  Default: ``None``
        :param timeout: Timeout to wait for pipeline launch.  Default: ``25``
        :param block: Plock on pipeline launch.  Default: Mo() setting
        :param rtmp_output: Provide RTMP output for pipeline.  Default: Mo() setting        
        :param kwargs: Additional arguments to be passed in API call, see Mosami API docs
        """

        if "block" not in kwargs:
            kwargs["block"] = self.block_on_launch
        if "rtmp_output" not in kwargs:
            kwargs["rtmp-output"] = self.rtmp_output

        # launch a pipeline
        kwargs["app_id"] = kwargs.get("app_id", self.app_id)
        kwargs["app_key"] = kwargs.get("app_key", self.app_key)
        pipeline = MoLaunch(
            pipeline_name,
            self.msg_connections,
            self.mo_server,
            rx_msg_callback=rx_msg_callback,
            main_msg_callback=self._master_rx_msg_callback,
            user_params=user_params,
            pipeline_state_callback=pipeline_state_callback,
            pipelines=self.pipelines,
            **kwargs
            )

        if pipeline.id not in self.pipelines:
            self.pipelines[pipeline.id] = [pipeline]
        else:
            self.pipelines[pipeline.id].append(pipeline)

        # Check state of pipeline
        pipeline.msg("get-state")

        # if pipeline_state_callback is defined, don't wait here for response
        if self.block_on_state:
            try:
                # spin here for a while, wait for pipeline to get to playing state
                timer = 0
                last_state = ""
                while pipeline.state != "playing" and timer < timeout:

                    if pipeline.state == "error":
                        self.log.error("Pipeline [%s] State: [%s]" % (pipeline.id,
                                       self.pipeline.state))

                        raise Exception("Pipeline state error: %s"
                                        % pipeline.last_state_message)

                    if last_state != pipeline.state:
                        self.log.info("Pipeline [%s] State: [%s]" % (pipeline.id,
                                      pipeline.state))
                        last_state = pipeline.state
                    time.sleep(0.05)
                    timer = timer + 0.05
            except Exception, inst:

                self.log.info("Error [%s] " % inst)
                raise Exception(inst)

            self.log.info("Pipeline [%s] State: [%s]" % (pipeline.id,
                          pipeline.state))

        return pipeline

    def shutdown(self):
        """ Shutdown all pipelines managed by this Mo() instance """

        for pls in self.pipelines:
            for pipeline in self.pipelines[pls]:
                pipeline.terminate()


class MoLaunch:

    """Pipeline class instantiation - each MoLaunch() instance represents a Mosami pipeline

    This class should not be instantiated direction, instead use of it's methods is through :class:`moutil.Mo()`

    :param pipeline_name: API name of MoLaunch pipeline
    :param msg_connections: Existing stomp message connections 
    :param mo_server: Mosami server to use
    :param rx_msg_callback: User-defined message callback
    :param user_params: User-parameters (optional) returned in callback
    :param main_msg_callback: 'master' message callback from stomp listener
    :param pipeline_state_callback: Callback for pipeline state messages 
    :param pipelines: Dict containing all pipelines currently managed (for duplicate tracking)
    :param app_id: APPLICATION auth ID
    :param app_key: APPLICATION auth KEY
    
    """

    def __init__(
        self,
        pipeline_name,
        msg_connections,
        mo_server,
        rx_msg_callback=None,
        user_params=None,
        main_msg_callback=None,
        pipeline_state_callback=None,
        pipelines=None,
        app_id="",
        app_key="",
        **kwargs
        ):

        self.msg_connections = msg_connections
        self.rx_msg_callback = rx_msg_callback
        self.main_msg_callback = main_msg_callback
        self.pipeline_state_callback = pipeline_state_callback
        self.app_id = app_id
        self.app_key = app_key
        self.pipeline_name = pipeline_name
        self.params = kwargs
        self.log = logging.getLogger()
        self.id = None
        self.mo_server = mo_server
        self.user_params = user_params

        self.state = "init"
        self.last_state_message = "Starting up"

        # if we have a  key with an underbar, add the same one as a -
        dashparams = {}
        if "app_id" not in self.params:
            self.params["app_id"] = self.app_id
        if "app_key" not in self.params:
            self.params["app_key"] = self.app_key
        for key in self.params:
            if "_" in key:
                dashkey = key.replace("_", "-")
                dashparams[dashkey] = self.params[key]
        self.params = dict(dashparams.items() + self.params.items())

        try:
            res = self._urlload(self.mo_server + "/jlaunch/%s" % pipeline_name,
                                self.params)
        except Exception, inst:
            self.log.error("Molaunch service not available on %s" % self.mo_server)
            self.log.error("Exception: %s" % inst)
            raise Exception("Molaunch service not available on %s" % self.mo_server)
        if len(res) == 2:
            res = res[0]
        # TODO - better error checking
        if "status" not in res:
            self.log.error("Serious error, launcher did not return status")
            raise StandardError("launcher did not return status")
        if res["status"] == "error":
            if "message" in res:
                reason = res["message"]
            elif "reason" in res:
                reason = res["reason"]
            elif "state" in res:
                reason = res["state"]
            else:
                reason = "pipeline error"
            self.log.error("Error launching pipeline: %s" % reason)
            raise StandardError("Error launching pipeline: %s" % reason)
        if "id" not in res:
            self.log.error("Error launching pipeline, return data: %s" % res)
            raise StandardError("Error launching pipeline, return data: %s" % res)
        if "warning" in res["status"]:
            self.log.warning("Warning launching pipeline : %s" % res["state"])

        self.id = res["id"]
        self.msgtopic = "%s.%s" % (self.params["app_id"], self.id)

        self.log.info("Launched id:%s, pipeline:%s, params:%s" % (self.id,
                      self.pipeline_name, self.params))

        # connect to pipeline for messaging
        pl_stomp_server = res["stomp_server"]
        self.stomp_server = pl_stomp_server

        if pl_stomp_server not in self.msg_connections:
            self.msg_connections[pl_stomp_server] = \
                StompMessageClient(pl_stomp_server, self.msgtopic,
                                   self.params["app_id"], self.params["app_key"],
                                   rx_msg_callback=self.main_msg_callback)

        if self.id not in pipelines:
            self.msg_connections[pl_stomp_server].subscribe(self.msgtopic)
        self.stomp = self.msg_connections[pl_stomp_server]

    def terminate(self):
        """Terminate a pipeline"""

        res = {}
        # should unsubscribe here
        self.msg_connections[self.stomp_server].unsubscribe(self.msgtopic)
        if self.id != "":
            try:
                # res = self._urlload(self.mo_server + '/terminate/%s' % self.id, {})
                res = self._urlload(self.mo_server + "/terminate",
                                    {"app_id": self.params["app_id"],
                                    "app_key": self.params["app_key"],
                                    "id": self.id})
            except Exception, inst:
                self.log.error("Error terminating %s: %s", self.id, inst)
        return res

    def msg(self, command, **kwargs):
        """
        Send a message to a pipeline
        
        :param command: Command to send to pipeline
        :param kwargs: Arguments for command (see API docs)
         """

        res = {}
        params = kwargs
        params = self._dashize(params)
        try:
            params["command"] = command
            self._send_message(params)
            self.log.debug("Send msg to id:%s, command:%s, params:%s" % (self.id,
                           command, params))
        except Exception, inst:
            self.log.error("Error [%s] trying to send command [%s] to id %s: %s"
                           % (inst, command, self.id, params))
        return res

    def set_properties(self, **kwargs):
        """Set properties of a pipeline
        
        :param kwargs: Arguments for set-properties API call (See API docs)
        """

        res = {}
        try:
            props = kwargs
            props = self._dashize(props)
            props["command"] = "set-properties"
            self._send_message(props)
            self.log.debug("Setting properties of id:%s, props:%s" % (self.id,
                           props))
        except Exception, inst:
            self.log.error("Error [%s] trying to set properties %s of id %s"
                           % (inst, props, self.id))
        return res

    def get_properties(self):
        """
        Returns properties of the pipeline in a dict()
        """

        res = {}
        try:
            res = self._urlload(self.mo_server + "/get-properties/%s" % self.id, {})
            self.log.info("Getting properties of id:%s" % self.id)
        except Exception, inst:
            self.log.error("Error trying to get properties of id %s: %s" % (inst,
                           self.id))
        return res

    def _send_message(self, msg):
        self.log.debug("Sending: %s" % msg)
        msg["id"] = self.id
        try:
            jsonmsg = json.dumps(msg)
        except:
            for key in msg:
                msg[key] = str(msg[key])
            jsonmsg = json.dumps(msg)
        try:
            self.stomp.send_message(jsonmsg + "\n", destination=self.msgtopic)
        except Exception, inst:
            self.log.error("Sending message failed : %s:  %s" % (type(inst), inst))

    def _urlload(self, url, params):
        proxy_handler = urllib2.ProxyHandler({})
        args = urllib.urlencode(params)
        req = urllib2.Request(url, args)
        opener = urllib2.build_opener(proxy_handler)
        try:
            f = opener.open(req, timeout=25)
            res = json.load(f)
        except Exception, inst:
            self.log.error("urlload error: %s" % inst)
            res = {}
            raise Exception
        return res

    def _dashize(self, params):
        dashparams = {}
        for key in params:
            if "_" in key:
                dashkey = key.replace("_", "-")
                dashparams[dashkey] = params[key]
        params = dict(dashparams.items() + params.items())
        return params


class StompMessageClientListener(object):

    def __init__(self, rx_message_callback):
        self.rx_message_callback = rx_message_callback

    def on_error(self, headers, message):
        print "received an error", message
        print "headers:", headers

    def on_message(self, headers, message):
        if self.rx_message_callback:
            self.rx_message_callback(headers, message)


#
# StompMessageClient() is intended to replace tcp long-term as the messaging infrastructure
# for now we'll support both, but use stomp for internal transactions
#

class StompMessageClient(object):

    def __init__(
        self,
        stomp_server,
        stomp_destination,
        app_id,
        app_key,
        rx_msg_callback=None,
        ):
        mqs = stomp_server.split(":")
        self.stomp_destination = stomp_destination
        self.log = logging.getLogger()
        self.log.setLevel(logging.INFO)
        self.stomp = stomp.Connection([(mqs[0], int(mqs[1]))], user=app_id,
                                      passcode=app_key)
        self.stomp_listener = StompMessageClientListener(rx_msg_callback)
        self.stomp.set_listener("pll", self.stomp_listener)
        self.stomp.start()
        self.stomp.connect()

    def subscribe(self, topic):
        try:
            self.stomp.subscribe(destination="/topic/%s.pipeline" % topic, ack="auto"
                                 )
        except:
            pass

    def subscribe_generic(self, topic):
        self.stomp.subscribe(destination="/topic/%s" % topic, ack="auto")

    def unsubscribe_generic(self, topic):
        self.stomp.unsubscribe(destination="/topic/%s" % topic, ack="auto")

    def unsubscribe(self, topic):
        self.stomp.unsubscribe(destination="/topic/%s.pipeline" % topic)

    def send_message(self, msg, destination=None):
        if not destination:
            destination = "/topic/%s.control" % self.stomp_destination
        else:
            stompdest = "/topic/%s.control" % destination
        try:
            self.stomp.send(msg, destination=stompdest)
        except Exception, inst:
            self.log.error("send message couldn't send to stomp %s" % inst)

    def shutdown(self):
        """Shutdown stomp connection"""

        try:
            self.stomp.disconnect()
        except:
            self.log.warning("Stomp could not disconnect - already disconnected?")


