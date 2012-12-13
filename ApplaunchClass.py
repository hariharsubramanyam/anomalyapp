#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
.. module:: ApplaunchClass
   :platform: Unix, Windows
   :synopsis: Inherit your class from this base to make a class that's applaunch-able.

.. moduleauthor:: Jim McGowan

"""

import logging
import sys
import urllib
import urlparse
import uuid
import inspect
import os
import atexit
import time

from moutil import Mo

import threading


class TimedCallback(threading.Thread):

    """Trigger a callback on a timer.
    
       Functional equivalent of setInterval() in javascript.
       
       >>> tcb = TimedCallback(callback=<my_callback_method>, [interval=<interval_in_seconds>, [**params]])
       >>> tcb.start()
       >>> ...do something else...
       >>> tcb.stop()
       
       The above example will trigger <my_callback_method> at interval seconds, where interval 
       is a floating-point number in seconds and defaults to 1.0.
    """

    def __init__(self, callback, **parameters):
        """Set default callback interval, and default parameters to forward to callback.
        
           Arguments:
               callback, required, name of method to trigger
               interval, optional, default=1.0, interval in seconds between callbacks  
               **parameters, optional different parameters to pass to callback.
        """

        threading.Thread.__init__(self)
        self._finishedFlag = threading.Event()
        self.defaults = {"interval": 1.0}
        self.callback = callback
        self.update(**parameters)
        self.setDaemon(1)

    def set_interval(self, interval):
        """Change number of seconds of sleep between callbacks.
           Arguments:
               interval, interval in seconds between callbacks
           Takes effect following the next callback.  To break
           a long callback interval, call stop(), set_interval(), and start() again.
        """

        self.defaults["interval"] = interval

    def update(self, **parameters):
        """Change default parameters forwarded to callback.
           Arguments:
               **parameters, optional parameters to pass to callback.
        """

        self.defaults.update(parameters)

    def stop(self):
        """Stop at next callback."""

        self._finishedFlag.set()

    def run(self):
        """Main callback-triggering loop."""

        try:
            while True:
                # return if stopped
                if self._finishedFlag.isSet():
                    return
                # trigger callback
                self.callback(**self.defaults)
                # set up next callback
                self._finishedFlag.wait(self.defaults["interval"])
        except KeyboardInterrupt:
            raise


class ApplaunchClass(object):

    """Base class for applaunch code.
    
    Inherit from this class to build code that can be launched with :mod:`applaunch`.

    You may need to override :func:`__init__`.
    You will probably not need to override :func:`shutdown`.
    """

    def __init__(self, log, **launch_params):
        """A simple class for using Mosami.

            log (logging): python logger.  Available to derived classes as self.log.
            
        Optional args:
            app_id (str), default=$MO_APP_ID: app_id for authentication.
            app_key (str), default=$MO_APP_KEY: app_key for authentication.
            All other optional parameters are available if you override this function.
            
        The class constructor creates a Mo class object with the provided developer
        key, self.mo.  You use self.mo in your public functions to access the Mosami API.
        
        The log parameter is available in self.log. 
        
        """

        self.log = log
        self.state = {}
        self.app_id = launch_params.get("app_id", os.getenv("MO_APP_ID", None))
        self.app_key = launch_params.get("app_key", os.getenv("MO_APP_KEY", None))
        self.app_starttime = launch_params.get("app-starttime", int(time.time()
                * 1000))
        self.mo = Mo(app_id=self.app_id, app_key=self.app_key)
        atexit.register(self.shutdown)
        self._methods = [x for x in dir(self) if not x.startswith("__")]

    def init(self, **parameters):
        """Your optional init function, triggered automatically after __init__.
        
        Optional args:
            All key=value arguments are available to your override method.
            
        Returns:
            By default, JSON indicating success with a uri to the client.
            
        This method is for initialization code, and you would typically override it.
        The advantages of overriding this, rather than __init__, is that:
            * __init__ can't return a value, so you can't relay errors. 
            * your __init__ would need call a super() function to run the baseclass __init__.
        """

        return self.return_success()

    def add_client_stream(self, **kwargs):
        """Your optional add_client_stream function, typically triggered when a source stream is available.
        
        Optional args:
            block (str, None):  See notes below.
            All other parameters are sent to the client.
            
        Returns:
            By default, JSON indicating a warning with an echo back of the supplied arguments.
            
        Through this method, applaunch will act as a broker for stream names between your 
        client and sever applications, and will coordinate launching of :doc:`modules` that 
        depend upon those streams.

        Blocking is necessary, because calls to `jlaunch` require the sources to exist, and will
        only retry for 5 seconds, and calls to :doc:`Mix`, :doc:`LayoutMix` or :doc:`GroupMix`
        will wait 15 seconds for adds.  When calling this, applaunch will block PRIOR to this
        function being executed.  So, on your client side when you call add_client_streams, the
        function here will not be triggered until <stream> given in the optional block=<stream> 
        parameter is available.

        Application-specific information may be returned in the JSON.  The return goes to
        :doc:`applaunch`.  See the :doc:`applaunch` for details of how to get that information
        to pull-only clients, such as javascript or PHP clients.               
        """

        return self.return_warning("add_client_stream not supported",
                                   args=self._clean_args(**kwargs))

    def delete_client_stream(self, **kwargs):
        """Your optional delete_client_stream function.
        
        This template function is provided because it is typically available in demo classes.
        Other tools for hosting the demo class can assume it is here, even if you don't override
        or support it.
        
        Returns:
            By default, JSON indicating a warning with an echo back of the supplied arguments.
        """

        return self.return_warning("delete_client_stream not supported",
                                   args=self._clean_args(**kwargs))

    def command(self, method, **kwargs):
        """Run user-supplied methods.

        OBSOLETE OBSOLETE OBSOLETE OBSOLETE OBSOLETE OBSOLETE OBSOLETE OBSOLETE OBSOLETE OBSOLETE
        
        Any public methods you add to this class will be called through the 'command' interface.
        
        Args:
            command (str): name of one of the methods you have added to this class.
            All other arguments are passed to your method.
            182
            
        Returns:
            Return of your public method, or JSON with {'status':'error',...} if the function doesn't exist.
            
        Raises:
            KeyboardInterrupt
            Returns '%s'%Exception for all other exceptions. 
        """

        self.log.info("received command:%s" % method)
        if method in self._methods:
            try:
                return getattr(self, method)(**self._clean_args(**kwargs))
            except KeyboardInterrupt:
                raise
            except Exception, inst:
                return self.return_error("Unhandled exception", exception="%s"
                                         % inst)
        else:
            return self.return_error("Unknown command.", command=method,
                                     method=self._methods)

    def GET_response(self, **kwargs):
        """Helper function for constructing responses to HTTP/1.1 GET requests.
        
        Optional args:
            All arguments are passed to your GET function.
            
        Returns:
            By default, JSON indicating success with a uri to the client.
            
        This method is for initialization code, and you would typically override it.
        """

        get = {
            "result": "success",
            "method": "GET",
            "type": self.__class__.__name__,
            "app-starttime": self.app_starttime,
            }
        get.update(self._clean_args(**kwargs))
        return get

    def GET(self, **kwargs):
        """Default function for replying to GET responses.
        
        Returns:
            If a self.state variables exists, it returns it as a properly formatted
            response (see GET_response).  Otherwise an empty, valid response is
            given.
            
        You can override this.  If you use a variable called self.state in your class
            for all relevant information, you don't need to.
        """

        return self.GET_response(**self.state)

    def shutdown(self):
        """Terminate all Mosami pipelines.
        Args:
        
            None.
            
        Returns:
        
            None.
        """

        self.mo.shutdown()

    def return_success(self, **kwargs):
        """Convenience function to return appropriate JSON when your public function is successful.
        
        Optional args:
        
            All key=value arguments are added as key:value pairs to your return.
            
        Returns:
        
            {'status':'success', 'command':method} and the optional key:value pairs
        """

        msg = {"status": "success", "command": inspect.stack()[1][3]}
        msg.update(self._clean_args(**kwargs))
        return msg

    def return_error(self, error_msg, **kwargs):
        """Convenience function to return appropriate JSON when your public method encounters an error.
        
        Args:
        
            error_msg (str): message identifying the error
            kwargs: set of key=value pairs you wish to add.
            
        Returns:
        
            {'status':'error', 'command':method, 'error':error_msg} and the optional key:value pairs
        """

        msg = {"status": "error", "command": inspect.stack()[1][3],
               "error": error_msg}
        msg.update(self._clean_args(**kwargs))
        return msg

    def return_warning(self, warning_msg, **kwargs):
        """Convenience function to return appropriate JSON when your public method wants to provide a warning.
        
        Args:
        
            warning_msg (str): message identifying the warning
        
        Optional args:
            
            All additional key=value arguments are added as key:value pairs to your return.
            
        Returns:
        
            {'status':'warning', 'command':command, 'warning':warning_msg} and the optional key:value pairs
        """

        msg = {"status": "warning", "command": inspect.stack()[1][3],
               "warning": warning_msg}
        msg.update(self._clean_args(**kwargs))
        return msg

    def assign_stream_name(self, arg, args):
        """Convenience function to name Mosami streams.
        
        OBSOLETE OBSOLETE OBSOLETE OBSOLETE OBSOLETE OBSOLETE OBSOLETE OBSOLETE OBSOLETE 
        
        Args:
        
            arg (str): key in args to assign a name, such as 'pub_name', 'play_name', or anything else.
            args (dict): arguments that may contain the key arg.
            
        Returns:
            
            varies. args[arg]
                        
        Example:
            args = assign_stream_name('pub_name',args)
            
        If args[arg] exists, nothing is changed.  If args[arg] does not exist,
        a uuid is created.  There is a default uuid function.  You may create
        your own uuid function(s) in class, and indicate in args['uuid_func']
        which function should be used.  Your uuid_func will be passed the args,
        and should return a str.  See :func:`default_uuid`.  
        """

        uuid_func = args.get("uuid_func", "default_uuid")
        return args.get(arg, getattr(self, uuid_func)(args))

    def default_uuid(self, args={}):
        """Generate a UUID
        
        OBSOLETE OBSOLETE OBSOLETE OBSOLETE OBSOLETE OBSOLETE OBSOLETE OBSOLETE OBSOLETE 
        
        Args:
        
            args (dict): Arguments passed to your public function.
            
        Returns:
        
            str.  a uuid.
        
        """

        return str(uuid.uuid4())

    def _clean_args(self, **args):
        """Internal routine.  Removes arguments that are unnecessary, and may prevent problems downstream.
        
        Optional Arguments:
            Any key=value argument is valid.
        
        Returns:
            All key=value arguments that are not on a black list.
        """

        for bad_arg in [
            "-host",
            "-path",
            "-remote-addr",
            "_host",
            "_path",
            "_remote_addr",
            "block",
            "command",
            "pl",
            ]:
            if bad_arg in args:
                del args[bad_arg]
        return args

    def auto_init_state(self, args):
        """Create a state dict from a default dictionary.
        
        Args:
            Dictionary of defaults key-value pairs.
            
        Returns:
            The input dictionary keys with all values set to None.  
            
        The JSON equivalent of None is null, so in applaunch, the values will 
        appear as the value null.
                
        Use this function to create a state variable from a set of defaults.
        For instance, for
        
            self.defaults = dict(
                                 src='person1',
                                 dst='my_app_stream'
                                 )
            
        the line
        
            self.state = self.auto_init_state(self.defaults)
            
        is the same as
        
            self.state = dict(
                              src=None,
                              dst=None
                              )
                              
        Note that the value for app-starttime is not changed.
        """

        return dict([[key, None] for key in args])


