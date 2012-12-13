;
// <queue> The following vars/functions will hold a set of functions and execute them once geoflash has returned.
// Then it will switch the function wrapper to one that executes immediately.
var moClient = {
	cameraStatusCallback: null,
	flashServerPlay: 'rtmp://ppc.mosami.com/live',
	flashServerPub: 'rtmp://ppc.mosami.com/live',
	execute_function: null,
	execution_queue : { contexts:[], params:[], funcs:[] },
	enqueue_function : function(context, params, func) {
		moClient.execution_queue.contexts.push(context);
		moClient.execution_queue.params.push(params);
		moClient.execution_queue.funcs.push(func);
	},
	execute_queue : function() {
		moClient.execute_function = moClient.immediate_execution;
		while( moClient.execution_queue.contexts.length > 0 ) {
			var context = moClient.execution_queue.contexts.shift();
			var params = moClient.execution_queue.params.shift();
			var func = moClient.execution_queue.funcs.shift();
			moClient.execute_function(context, params, func);
		}
	},
	immediate_execution : function(context, params, func) {
		func.apply(context, [params]);
	}
};
;(function($) {
  	$.fn.moClient = function(opts) {
  		var $this = this;
  		var defaults = {
			inner_play_div: 'playobj_' + (Math.floor(Math.random()*100000000)).toString(),
  			inner_cam_div: 'pubobj_'+ (Math.floor(Math.random()*100000000)).toString(),
			pub_retry: 1000,
			pub_timeout: 100000,
			captureParam: { flashVars: "camheight=240&camwidth=320&backgroundColor=000000" },
  			camera_started: false,
  			flash_camera: false,
  			geoflash: false
	  	};
  		var params = $.extend({}, defaults, opts);
		var pub_func_count = 0;
		var pub_func_set_interval = null;
		pub_func = function(pub_path, pub_name, inner_cam_div) {
			try {
				console.log('trying to pub:' + pub_path + '/' + pub_name);
  				var flash_camera = getFlashMovie(inner_cam_div);
				flash_camera.publish(pub_path, pub_name);
				if (pub_func_set_interval != null) clearInterval(pub_func_set_interval);
				console.log("pubbed:" + pub_path + '/' + pub_name);
			} 
			catch(err) {
				if( err == 'TypeError: flash_camera.publish is not a function' || err.name=='TypeError') {
					pub_func_count = pub_func_count + 1;
					if( pub_func_count < 25 ) {
						console.log('retrying pub...');
					} else {
						if (pub_func_set_interval != null) clearInterval(pub_func_set_interval);
						console.log("Could not publish.");
					}
				} else {
					if (pub_func_set_interval != null) clearInterval(pub_func_set_interval);
					console.log("Received an unknown error trying to publish:");
					console.log(err);
					throw err;
				}
			}
		}
		// Use geoflash to determine player, etc.
		if( params.geoflash == true && $("#geoflash").length == 0 ) {
			console.log("using geoflash");
			moClient.execute_function = moClient.enqueue_function;  // after geoflash is loaded, this will be set to immediate_execution
			$("body").append("<div id='geoflash'></div>");
			var flash_vars = {'url':moClient.flashServerPlay};
  			swfobject.embedSWF("moClient/geoflash.swf", 'geoflash', "1", "1", "11.1.0", "", flash_vars, {}, {},  
  	  				function(status) { console.log("geoflash embeded"); }
  			);
		} else {
			if( params.geoflash == false ) {
				console.log("not using geoflash");
				moClient.execute_function = moClient.immediate_execution;
			} else {
				console.log("geoflash already started.");
			}
		}
  		return {
  			params: params,
	  		startCam: function(pub_id, pub_key, func_opts) {
	  			moClient.execute_function(this, func_opts, function(func_opts) {
		  			func_opts = func_opts || {};
		  			func_opts.callback = func_opts.callback || function(status) { console.log('camera started'); }
		  			if( this.params.camera_started == false ) {
			  			var func_opts = func_opts || {};
			  			if( func_opts.cameraStatusCallback ) {
			  				moClient.cameraStatusCallback = func_opts.cameraStatusCallback;
			  			}
			  			$this.append('<div id="'+defaults.inner_cam_div+'">player loading...</div>');
			  	  		var $params = this.params;
			  	  		width = func_opts.width || '320';
			  	  		height = func_opts.height || '240'; 
			  	  		$params.captureParams = { flashVars: 'camheight='+height+'&camwidth='+width+'&backgroundColor=000000&app_id='+pub_id+'&app_key='+pub_key };
			  	  		console.log($params.captureParams);
			  	  		swfobject.embedSWF("moClient/ImmCamera.swf", $params.inner_cam_div, "100%", "100%", "11.1.0", "", {}, $params.captureParams, {},  
			  	  				function(status) {
						  	  		$params.camera_started = true;
									func_opts.callback(status);
								}
			  	  		);
		  			}
	  			});
		  	},
			stopCam: function() {
				moClient.execute_function(this, {}, function() {
					if( this.params.camera_started ) {
						var flash_camera = getFlashMovie(this.params.inner_cam_div);
						flash_camera.stopCamera();
						$('#asplay').remove();
						this.params.camera_started = false;
					}
				});
			},
		  	publish: function(pub_name, pub_id, pub_key, func_opts) {
		  		moClient.execute_function(this, func_opts, function(func_opts) {
		  			var func_opts = func_opts || {};
		  			if( moClient.flashServerPub ) {
		  				var pub_path = moClient.flashServerPub + '/' + pub_id;
		  			} else {
		  				var pub_path = '';
		  			}
		  			console.log('pub_path:'+pub_path);
	  				var inner_cam_div = this.params.inner_cam_div
			  		// Publish will start the camera if it isn't already running.
		  			if( this.params.camera_started == false ) {
		  				var user_cb = func_opts.cameraStatusCallback || function(status) { console.log('default cb:'); console.log(status); }
		  				func_opts.cameraStatusCallback = function(status) {
		  					user_cb(status)
		  					try {
		  						if( status=='Camera.Unmuted') {
			  						pub_func_set_interval = setInterval(function() { pub_func(pub_path, pub_name, inner_cam_div), 100 });
			  					} else {
			  					}
		  					} catch(err) {
		  						console.log("Error in jquery.moClient.js:"+err)
		  					}	  								  				}
		  				this.startCam(pub_id, pub_key, func_opts);
		  			} else {
	  					pub_func_set_interval = setInterval(function() { pub_func(pub_path, pub_name, inner_cam_div), 10 });
		  			}
		  		});
	  		},
	  		unpublish: function() {
		  		moClient.execute_function(this, {}, function() {
	  				var flash_camera = getFlashMovie(this.params.inner_cam_div);
					flash_camera.unpublish();
		  		});
	  		},
	  		player_start: function(stream_name, play_id, play_key, play_opts, attrib_opts) {
	  			moClient.execute_function(this, play_opts, function(play_opts) {
		    		play_opts = play_opts || {};
		    		attrib_opts = attrib_opts = {};
	  				$this.append('<div id="'+this.params.inner_play_div+'">player loading...</div>');
			    	if( moClient.flashServerPlay) { 
			    		var src = moClient.flashServerPlay + '/' + play_id + '/' + stream_name; 
			    	} else { 
			    		var src = stream_name; 
			    	}
		    		var swfVersionStr = "10.0.0";
		    		var flashvars2 = {'src':moClient.flashServerPlay+'/'+play_id+'/'+stream_name,
		    						  'mouseHandler':"mouser", 'enableStatusBox':true};
		    		flashvars2.app_id = play_id;
		    		flashvars2.app_key = play_key;
		    		$.extend(flashvars2,play_opts);

		    		var params = {};
		            params.quality = "high";
		            params.bgcolor = "000000";
		            params.mouseHandler = "mouser";
		            params.allowscriptaccess = "always";
		            params.allowfullscreen = "true";
		            $.extend(params,play_opts);
		            
		            var attributes = {};
		            attributes.id = "asplay";
		            attributes.name = "asplay";
		            attributes.align = "middle";
		            $.extend(attributes,attrib_opts);
		            
		            swfobject.embedSWF(
			            "moClient/asplay.swf", this.params.inner_play_div, 
		                "100%", "100%", swfVersionStr, "", 
		                flashvars2, params, attributes);

		            // JavaScript enabled so display the flashContent div in case it is not replaced with a swf object.
		            swfobject.createCSS("#flashContent", "display:block;text-align:left;");
	  			});
	  		},
	  		player_stop: function() {
	  			moClient.execute_function(this, {}, function(func_opts) {
	  				$('#asplay').remove();
	  			});
	  		}	
		}
	}
})(jQuery);

function cameraReady(status) {
	console.log("CameraReady:"+status);
	moClient.cameraStatusCallback(status);
}

function getFlashMovie(movieName) {
	obj = document[movieName] ? document[movieName] : window[movieName]
	if( obj===undefined ) {
		throw "Unsupported browser";
	}
	return obj
}

function flashServerInfo(objectId, results) {
    if (results == 'timeout') {
    	console.log('geoflash server timeout, using defaults:'+moClient.flashServerPub+", "+moClient.flashServerPlay);
    } else {
        console.log("geoflash info:"+results);
    	moClient.flashServerPlay = results[0];
    	moClient.flashServerPub = results[1];
    }
    moClient.execute_function = moClient.immediate_execution;
    moClient.execute_queue();    
}

function onJavaScriptBridgeCreated(playerId) {
	console.log("playerId:"+playerId);
}
function playStatus(status) {
	console.log("play " +
			""+status);
}
function mouser(obj) {
	var output = '';
	for (property in obj) {
	  output += property + ': ' + obj[property]+'; ';
	}
	console.log('mouser: '+output)
}
