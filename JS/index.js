
var $anomalyDivMoClient;
var $anoOne;
var $anoTwo;
var $anoThree;
var globals = new Object();

globals.appKey = "95f61d2482bf35715ae619784999a6ff";
globals.appId = "4457c42e";

globals.timeStep = 0;
globals.anolomousMix = "mix1";
globals.anomalyOne = "crowd1";
globals.anomalyTwo = "crowd2";
globals.anomalyThree = "crowd3";
globals.anomalyVid = "crowd2";

globals.BASE = "crowd";
globals.NUMVIDS = 4;
globals.VIDEOPOS = [[42.35829955919554,-71.09455624209659],
[42.35914044808386,-71.09342971431033],
[42.35880969979702,-71.09462061511294],
[42.35866955169272,-71.09363356219546],	// 4
[42.35912923630605,-71.09169700728671],
[42.358411678364135,-71.09141269313113],
[42.35773335433812,-71.09195449935214],
[42.357559567665554,-71.09269478904025], // 8
[42.35863905340927,-71.09413540310925],
[42.35808409189092,-71.0914961094386]
];


$(document).ready(function(){
	$anomalyDivMoClient = $("#anoVid").moClient();
	$anoOne = $("#divFirst").moClient();
	$anoTwo = $("#divSecond").moClient();
	$anoThree = $("#divThird").moClient();
	//$("#myModal").modal('show');
	
	makeMapAndVM();
	
	addVideos(function(){
		makeMixes(1,function(){
			setInterval(function(){
				sendGET("anomalyDetect",buildParamString(1,globals.NUMVIDS,""),function(dat){
					maxAnomaly = 0;
					maxTriple = [0,0,0];
					maxAnomalies = ["crowd1","crowd2","crowd3"];
					globals.timeStep += 1;
					if(globals.timeStep%10==0){
						theStr =  $("#txtAnoClus").text().toString();
						console.log(theStr);
						theStr = theStr.replace("Anomalous ","");
						$("#txtPrevClus").text("Previous " + theStr);
					}
					for (var x = 0; x < globals.vm.videoNames.length; x++){
						for (key in dat){
							if (key == globals.vm.videoNames[x]){
								globals.vm.videoVals[x] = dat[key];
								if (maxAnomaly < globals.vm.videoVals[x]){
									globals.anomalyVid = key;
									maxAnomaly = globals.vm.videoVals[x];
								}
								if(globals.vm.videoVals[x] > maxTriple[2]){
									maxTriple[0] = maxTriple[1];
									maxTriple[1] = maxTriple[2];
									maxAnomalies[0] = maxAnomalies[1];
									maxAnomalies[1] = maxAnomalies[2];
									maxTriple[2] = globals.vm.videoVals[x];
									maxAnomalies[2] = key;
								}
								else if (globals.vm.videoVals[x] > maxTriple[1]){
									maxTriple[0] = maxTriple[1];
									maxAnomalies[0] = maxAnomalies[1];
									maxTriple[1] = globals.vm.videoVals[x];
									maxAnomalies[1] = key;
								}
								else if (globals.vm.videoVals[x] > maxTriple[0]){
									maxTriple[0] = globals.vm.videoVals[x];
									maxAnomalies[0] = key;
								}
							}
						}
					}
					globals.anolomousMix = globals.vm.resizeMarkers();
					globals.anomalyOne = maxAnomalies[2];
					globals.anomalyTwo = maxAnomalies[1];
					globals.anomalyThree = maxAnomalies[0];
					if(globals.timeStep%10==0){
						$("#txtAnoClus").text("Anomalous Cluster = " + globals.anolomousMix);
						setAnomalyVideo();
					}
				});
			},2000);
		});
	})
   	
   	$("#btnFirst").click(function(){
   		globals.vm.goToVid(globals.anomalyOne);
   	});
   	$("#btnSecond").click(function(){
   		globals.vm.goToVid(globals.anomalyTwo);
   	});
   	$("#btnThird").click(function(){
   		globals.vm.goToVid(globals.anomalyThree);
   	});
   	$("#btnGoToStream").click(function(){
   		globals.vm.goToVid(globals.anomalyVid);
   	});
});


function buildParamString(start,end,prepend){
	res = prepend;
	for(var i = start; i <= end; i++){
		res += globals.BASE + i;
		if (i != end){
			res += "|";
		}
	}
	return res;
}

function addVideos(callback){
	console.log(buildParamString(1,globals.NUMVIDS,""));
	sendGET("addVideo",buildParamString(1,globals.NUMVIDS,""),callback);
}

function makeMixes(i,callback){
	var numMixes = globals.NUMVIDS/4;
	console.log("HERE" + i);
	if(i == numMixes){
		sendGET("makeMix",buildParamString(4*i-3,4*i,"mix"+i+"|"),callback);
	}
	else{
		sendGET("makeMix",buildParamString(4*i-3,4*i,"mix"+i+"|"),function(){
			makeMixes(i+1,callback);
		});
	}
}

function sendGET(cmdType,argStr,callback){
	$.ajax({
		url: "http://localhost:8768/apps/myapp",
		dataType: 'json',
		data:"commandType="+cmdType+"&argString="+argStr,
		success: callback
	});
}

function makeMapAndVM(){
	var mapOptions = {
			center: new google.maps.LatLng(42.35862470423332,-71.09296837435977),
			zoom: 18,
			mapTypeId: google.maps.MapTypeId.HYBRID
		};
   	globals.map = new google.maps.Map(document.getElementById("map_canvas"),mapOptions);
   	globals.vm = new videoManager(globals.map);
   	globals.vm.placeMarkers();
   	
   	google.maps.event.addListener(globals.map,'click',function(e){
   		console.log(e.latLng);
   	});
   	
   	google.maps.event.addListener(globals.map, 'zoom_changed', function() {
    	if(globals.map.zoom > 16 && globals.vm.clusterMode){
    		globals.vm.clusterMode = false;
    		globals.vm.placeMarkers();
    	}
    	else if (globals.map.zoom <= 16 && !globals.vm.clusterMode){
    		globals.vm.clusterMode = true;
    		globals.vm.placeMarkers();
    		
    	}
  	});
}

function setAnomalyVideo(){
	$anomalyDivMoClient.player_stop();
	$anoOne.player_stop();
	$anoTwo.player_stop();
	$anoThree.player_stop();
	
	$("#btnFirst").text(globals.anomalyOne);
	$("#btnSecond").text(globals.anomalyTwo);
	$("#btnThird").text(globals.anomalyThree);
	
	$anoOne.player_start(globals.anomalyOne,globals.appId,globals.appKey);
	$anoOne.player_start(globals.anomalyTwo,globals.appId,globals.appKey);
	$anoOne.player_start(globals.anomalyThree,globals.appId,globals.appKey);
	$anomalyDivMoClient.player_start(globals.anolomousMix,globals.appId,globals.appKey);
	anomalyVid = globals.anolomousMix;
}

function videoManager(mp){
	 
	this.map = mp;
	
	// If true, replace videos with mixes
	this.clusterMode = false;

	this.videoPositions = globals.VIDEOPOS;
		
	// backup for mit streams
	//this.videoPositions = [[42.3611601026,-71.08679562817997],[42.36076371791946,-71.08703166257328],[42.36092227209176,-71.08838349591679],[42.36112839191758,-71.08791142713017],[42.360739934759096,-71.08884483586735],[42.35993922977393,-71.08785778294987],[42.35961418820488,-71.08888775121159],[42.36018499179524,-71.08926326047367],[42.36058930786782,-71.08963876973576],[42.36112839191758,-71.0891774297852],[42.361429642754416,-71.08984261762089],[42.3616753989463,-71.09022885571903],[42.36231753155566,-71.09025031339115],[42.35933671236438,-71.08723551045841],[42.358718333226086,-71.091484129538],[42.35610997476505,-71.09203130017704],[42.353533222569325,-71.09084039937443],[42.35718028692769,-71.09241753827519],[42.35782246547522,-71.09285742055363],[42.35913058666113,-71.09335094701237],[42.35873418917745,-71.09462767850346]];
	
	// will be something like ["crowd1","crowd2","crowd3"]
	this.videoNames = [];

	// this.videoVals[x] = the probability that the x-th video stream is NORMAL
	this.videoVals = [];
	
	// Initialize with 8 crowd videos (notice the for loop goes up until 8) and set each videoVal to 1 (not an anomaly)
	for (var vNum = 1; vNum <= globals.NUMVIDS; vNum++){
		this.videoNames.push(globals.BASE+vNum);
		this.videoVals.push(1);
	}
	for (var vNum = 1; vNum < globals.NUMVIDS/4; vNum++){
		this.videoNames.push("mix"+vNum);
		this.videoVals.push(1);
	}
	
	// array of the marker objects
	this.markers = [];
	
	// array of the infowindow objects
	this.infowindows = [];
	
	// default size of markers
	this.MARKER_SIZE = 10;
	
	// create markers
	for(var x = 0; x < this.videoPositions.length; x++){
		// set marker position and icon
		marker = new google.maps.Marker({
			position: new google.maps.LatLng(this.videoPositions[x][0],this.videoPositions[x][1]),
			title: "Marker " + x,
			icon: {
				path: google.maps.SymbolPath.CIRCLE,
				scale: this.MARKER_SIZE,
				strokeColor: "#FF1111"
			}
		});
		// add marker to markers array
		this.markers.push(marker);
		// create it's info window and add it to infowindow array
		this.infowindows.push(new google.maps.InfoWindow({
				content: ('<div style="height:100px;width:200px" id="' + this.videoNames[x] + '"></div">')
		}));
		// make the marker show it's video stream when clicked
		google.maps.event.addListener(marker,'click',(function(mrkers,i,vnms,infs,mmap){
				return function(){
					infs[i].open(mmap,mrkers[i]);
					var divName = "#" + vnms[i]; 
					setTimeout(function(){
						$(divName).css("background","#000000");
						var $player = $(divName).moClient();
						$player.player_start(vnms[i],globals.appId,globals.appKey);
					},1000)
				}
		})(this.markers,x,this.videoNames,this.infowindows,this.map));
	}

	
	// take boolArr like [true, true, false, true, ...] where if boolArr[i] = true, we show the i-th marker on the map
	this.setMarkers = function(boolArr){
		for(var x = 0; x < this.markers.length; x++){
			this.markers[x].setMap(null);
			if (boolArr[x]){
				this.markers[x].setMap(this.map);
			}
		}
	}
	
	// draw each marker on the grid
	this.placeMarkers = function(){
		paramArr = []
		for(var i = 0; i < globals.NUMVIDS; i++){
			paramArr.push(!this.clusterMode);
		}
		for(var i = 0; i < globals.NUMVIDS/4; i++){
			paramArr.push(this.clusterMode);
		}
		this.setMarkers(paramArr);
	}
	
	this.resizeMarkers = function(){
		mappers = this.Zs(this.videoVals);
		for (var x = 0; x < this.markers.length; x++){
			this.markers[x].setIcon({
				path: google.maps.SymbolPath.CIRCLE,
				scale: mappers[x]*this.MARKER_SIZE,
				strokeColor: "#FF1111"
			});
		}
		
		mixVals = [];
		
		for(var x = 1; x <= globals.NUMVIDS/4; x++){
			var avg = mappers[4*x-3] + mappers[4*x-2] + mappers[4*x-1] + mappers[4*x];
			mixVals.push(avg);
			this.markers[globals.NUMVIDS - 1 + x].setIcon({
				path: google.maps.SymbolPath.CIRCLE,
				scale: avg*0.5*this.MARKER_SIZE,
				strokeColor: "#FF1111"
			});
		}
		
		maxVal = 0;
		maxMix = 0;
		for(var i = 0; i < mixVals.length; i++){
			if(mixVals[i]>maxVal){
				maxVal = mixVals[i];
				maxMix = i+1;
			}
		}
		return ("mix"+maxMix);
	}
	
	
	this.Zs = function(arr){
		var mn = 0.0;
		for (var x = 0; x < arr.length; x++){
			mn += arr[x];
		}
		mn = mn/arr.length;
		var sd = 0.0;
		for (var x = 0; x < arr.length; x++){
			sd += (arr[x]-mn)*(arr[x]-mn);
		}
		sd = Math.sqrt(sd)/(arr.length-1);
		resultArr = [];
		z = 0.0;
		for (var x = 0; x < arr.length; x++){
			z = Math.abs((arr[x]-mn)/sd);
			if(z > 1.5){
				z = 1.5;
			}
			if(z < 0.5){
				z = 0.5;
			}
			resultArr.push(Math.abs(z));
		}
		return resultArr;
	}
	this.goToVid = function(vidName){
		var currMarker = null;
		var currInd = 0;
		for(var x = 0; x < this.videoNames.length; x++){
			if (this.videoNames[x] == vidName){
				currMarker = this.markers[x];
				currInd = x;
			}
		}
		this.map.setZoom(19);
		this.map.panTo(currMarker.position);
		this.infowindows[currInd].open(this.map,currMarker);
		var divName = "#" + vidName;
		setTimeout(function(){
			$(divName).css("background","#000000");
			var $player = $(divName).moClient();
			$player.player_start(vidName,globals.appId,globals.appKey); 
		},1000)
		
	
	}
}
