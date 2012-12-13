#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys
import os
import logging
import math
from ApplaunchClass import ApplaunchClass
import operator

class anomalyApp(ApplaunchClass):
    def init(self, **params):
        self.defaults = dict(src="person_moving_arms")
        self.defaults.update(params)
        self.state = self.auto_init_state(self.defaults)
        self.running = False
        
        self.mixes = {}
        self.vidNames = []
        
        return self.return_success(**self.state)
        
    def launchVideo(self,videoName):
        if not hasattr(self,"anomalyDetectors"):
            self.anomalyDetectors = {"emp":1}
        def outer(vName):
            if self.anomalyDetectors is None:
                self.anomalyDetectors = {"emp":1}
            def handleMsg(data):
                try:
                    self.anomalyDetectors[vName].update(data)
                except:
                    pass
            return handleMsg
        self.anomalyDetectors[videoName] = AnomalyDetector()
        vid = self.mo.jlaunch("LoopVideo",src=videoName + ".flv",dst=videoName)
        opti = self.mo.jlaunch("DetectMovement",src=videoName,dst=videoName+"Move",rx_msg_callback=outer(videoName))
        return (vid,opti)

    def launchMix(self,mixName, mixVids):
        theMix = self.mo.jlaunch("LayoutMix",dst=mixName)
        for mixVid in mixVids:
            theMix.msg("add",stream=mixVid)
        self.mixes[mixName] = [theMix,mixVids]

    def add_client_stream(self, **params):
        if self.running:
            self.delete_client_stream(**params)
        self.state.update(self.defaults)
        self.state.update(params)
        self.running = True
        return self.return_success(**self.state)

    def delete_client_stream(self, **params):
        if self.running:
            self.running = False
            return self.return_success(**self.state)
        else:
            return self.return_warning("Nothing running.  Call add_client_stream "
                                       "first.", **self.state)

    # The user communicates with this app using GET requests, so we handle them here
    def GET(self, **params):
        returnVal = {}  # the GET response message
        #try:
        commandType = params["commandType"] # can be addVideo, makeMix, or anomalyDetect
        if commandType == "addVideo":       # the user wants us to start recording motion vector data for a video
            argString = params["argString"] # this string tells us what videos to add. It takes the form "video1|video2|video3" for adding three videos
            vidsToAdd = argString.split('|')
            for vidToAdd in vidsToAdd:      # for each video, add it to our list and launch it
                self.vidNames.append(vidToAdd)
                self.launchVideo(vidToAdd)
            returnVal["wasSuccess"] = "Yes"
        elif commandType == "makeMix":      # create a mix of several videos
            argString = params["argString"]   # this string tells us what streams to add to the mix. It takes the form "mixName|stream1|stream2|stream3" for adding 3 streams
            mixVids = argString.split('|')
            mixName = mixVids[0]            # this is the name of the mix
            mixVids = mixVids[1:]           # ignore the first element because that's the name of the mix
            self.launchMix(mixName, mixVids)        # create the mix
            returnVal["wasSuccess"] = "Yes"
        elif commandType == "anomalyDetect": # run an anomaly detection
            argString = params["argString"] # this string tells us what streams we should run anomaly detection on
            anoStreams = argString.split('|')
            for anoStream in anoStreams:
                returnVal[anoStream] = 1 - self.anomalyDetectors[anoStream].anomalyDetect()
            returnVal["wasSuccess"] = "Yes"
        #except:      # In case of exception, indicate that something went wrong
        #    returnVal["wasSuccess"] = "No"
        return self.GET_response(**returnVal)
    
    def makeMix(self,streamNames,mixName):
        self.mixes[mixName] = self.mo.jlaunch("LayoutMix",dst=mixName)
        for i in xrange(2, len(streamNames)):
            self.mixStreams.append(streamNames[i])
            self.mixes[mixName].msg("add",stream=streamNames[i])
        
class Normalizer:
    def __init__(self):
        self.s = 0.0
        self.S = 0.0
        self.n = 0.0
    def update(self,x):
        self.s += x
        self.S += x**2
        self.n += 1
    def mean(self):
        return self.s/self.n
    def stdev(self):
        return math.sqrt((self.n*self.S-(self.s)**2)/(self.n*(self.n-1)))
    def z(self,v):
        return (v - self.mean())/self.stdev()
    def zprob(self,z):
        Z_MAX = 6.0 # maximum meaningful z-value
        if z == 0.0:
            x = 0.0
        else:
            y = 0.5 * math.fabs(z)
            if y >= (Z_MAX*0.5):
                x = 1.0
            elif (y < 1.0):
                w = y*y
                x = ((((((((0.000124818987 * w-0.001075204047) * w +0.005198775019) * w-0.019198292004) * w +0.059054035642) * w-0.151968751364) * w +0.319152932694) * w-0.531923007300) * w +0.797884560593) * y * 2.0
            else:
                y = y - 2.0
                x = (((((((((((((-0.000045255659 * y+0.000152529290) * y -0.000019538132) * y-0.000676904986) * y +0.001390604284) * y-0.000794620820) * y -0.002034254874) * y+0.006549791214) * y -0.010557625006) * y+0.011630447319) * y -0.009279453341) * y+0.005353579108) * y -0.002141268741) * y+0.000535310849) * y +0.999936657524
        if z > 0.0:
            prob = ((x+1.0)*0.5)
        else:
            prob = ((1.0-x)*0.5)
        return prob
    def valprob(self,v):
        return self.zprob(self.z(v))
class AnomalyDetector:
    def __init__(self,trainSet=20000):
        self.history = []
        self.ts = trainSet
        self.resetNormalizers()
    def resetNormalizers(self):
        self.R = Normalizer()
        self.L = Normalizer()
        self.U = Normalizer()
        self.D = Normalizer()
    def update(self, dat):
        self.history.append([dat["nRight"],dat["nLeft"],dat["nUp"],dat["nDown"]])
        if len(self.history) == self.ts:
            self.history.pop(0)
    def anomalyDetect(self):
        testingIndex = len(self.history) - self.ts
        if len(self.history) < self.ts:
            testingIndex = (9*len(self.history))/10
        self.resetNormalizers()
        testingVector = [0.0, 0.0, 0.0, 0.0]
        for x in xrange(0,testingIndex):
            self.R.update(self.history[x][0])
            self.L.update(self.history[x][1])
            self.U.update(self.history[x][2])
            self.D.update(self.history[x][3])
        
        counter = 0.0
        for x in xrange(testingIndex + 1, len(self.history)):
            counter += 1
            testingVector = [testingVector[i] + self.history[x][i] for i in xrange(0,4)]
        testingVector = [testingVector[i]/counter for i in xrange(0,4)]
        PR = self.R.valprob(testingVector[0])
        PL = self.L.valprob(testingVector[1])
        PU = self.U.valprob(testingVector[2])
        PD = self.D.valprob(testingVector[3])
        return (PR + PL + PU + PD)/4.0


if __name__ == "__main__":
    logging.basicConfig(format="%(levelname)s %(message)s", stream=sys.stdout,
                        level=logging.DEBUG)
    log = logging.getLogger("example")

    # get app_id, app_key from environmental variables

    app_id = os.getenv("MO_APP_ID")
    app_key = os.getenv("MO_APP_KEY")
    if not app_id or not app_key:
        log.error("You must set the MO_APP_ID and MO_APP_KEY "
                  + "environmental variables to run anomalyApp "
                  + "from the command line.")

    src = "person_moving_arms"
    dst = "output"
    if len(sys.argv) > 1:
        src = sys.argv[1]

    inst = anomalyApp(log, app_id=app_id, app_key=app_key)
    inst.init()
    raw_input(">>> press enter to stop <<<")
    inst.shutdown()
