anomalyapp
==========

Video anomaly identification and grouping with mosami.

To use, first go to MyENV directory and launch virtual environment

source bin/activate

then launch applaunch with the appId and appKey that we use.

python applaunch.py -i <appid> -k <appkey>

Then launch the application with appId = myapp

curl -X POST "http://localhost:8768/apps" -d "app=anomalyApp&appId=myapp"

Now open the web client (index.html in HTML directory)

The web client uses 8 videos + 8 detect movements + 2 mixes = 18 video streams launched. If cloud scaling is turned off, it may not work properly.

Once the video streams are launched, the  map markers should begin resizing according to anomaly level. Click the "About" tab on the nav-bar of the web client to learn more.
