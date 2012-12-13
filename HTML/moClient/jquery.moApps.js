// jquery interface to applaunch
;(function($) {
  	$.moApps = function(app_id, app_key, params, opts) {
		var default_opts = {
							success:function(json,defaults){console.log('default moApps callback: success');return;},
							error:function(json,defaults){console.log('default moApps callback: error');return;}
							}
		var default_params = {
							  url:'http://'+document.domain+':8768',
							  app_id:app_id,
							  app_key:app_key,
							  uri:null 
							  };
		if( document.domain.length==0 ) {
			default_params.url = 'http://127.0.0.1:8768';
		}
		var _params = $.extend(true, {}, default_params, params);
		var _opts = $.extend(true, {}, default_opts, opts);
		return {
			params: _params,
			opts: _opts,
		  	create: function(app, params, opts) {
		  		$this = this;
		  		if( app === undefined || typeof app !== 'string') {
		  			console.log("Can't create, no app given.");
		  			return {'status':'error','error':'App not given'}
		  		}
		  		var _params = $.extend({}, this.params, params);
		  		_params.app = app;
		  		var _opts = $.extend({}, this.opts, opts);
		  		_params._method = 'POST'
				$.post(this.params.url+'/apps', _params, function(response, textStatus) {
					if( response.result == 'success' ) {
						$this.params.uri = response.uri;
					}
  					if( _opts[textStatus] ){
  						_opts[textStatus](response,params);
  					}
				}, 'json');
			},
			terminate: function(opts) {
				var _params = $.extend(true, {}, this.params);
				var _opts = {} = $.extend(true, {}, this.opts, opts);
		  		_params._method = 'DELETE'; 
		  		$.post(this.params.url + this.params.uri, _params, function(data, textStatus) {
		  			if( _opts[textStatus] ){
		  				_opts[textStatus](data,_opts);
		  			}
		  		}, "json");
			},
			command: function(command, params, opts) {
				var _params = $.extend(true, {}, this.params);
				var _opts = {} = $.extend(true, {}, this.opts, opts);
				_params.command = command;
		  		_params._method = 'PUT';
		  		$.post(this.params.url + this.params.uri, _params, function(data, textStatus) {
		  			if( _opts[textStatus] ){
		  				_opts[textStatus](data,_opts);
		  			}
		  		}, "json");
			}
		}
	}
})(jQuery);
