#!/usr/bin/python
# -*- coding: utf-8 -*-

#
# Source: https://github.com/RyanMelenaNoesis/XbmcSecurityCamOverlayAddOn"
# and kodi forum discussion: https://forum.kodi.tv/showthread.php?tid=182540
#
# JSONRPC Call to trigger this script:
#
# curl -s -u <user>:<password> -H "Content-Type: application/json" -X POST -d '{"jsonrpc":"2.0","method":"Addons.ExecuteAddon","params":{"addonid":"script.securitycam"},"id":1}' http://<ip>:<port>/jsonrpc
# curl -X POST -H "Content-Type: application/json' -i http://<ip>:<port>/jsonrpc --data '{ "jsonrpc": "2.0", "method": "Addons.ExecuteAddon", "params": { "wait": false, "addonid": "script.securitycam", "params": { "streamid": "1"} }, "id": 1 }'
#

# Import the modules
import os, time, random, string, sys, platform
import xbmc, xbmcaddon, xbmcgui, xbmcvfs
import requests, subprocess
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
from threading import Thread

try:
    from urllib.request import build_opener, HTTPPasswordMgrWithDefaultRealm, HTTPBasicAuthHandler, HTTPDigestAuthHandler, Request
except ImportError:
    from urllib2 import build_opener, HTTPPasswordMgrWithDefaultRealm, HTTPBasicAuthHandler, HTTPDigestAuthHandler, Request

if sys.version_info.major < 3:
    INFO = xbmc.LOGNOTICE
    from xbmc import translatePath
else:
    INFO = xbmc.LOGINFO
    from xbmcvfs import translatePath

# Constants
ACTION_PREVIOUS_MENU = 10
ACTION_STOP = 13
ACTION_NAV_BACK = 92
ACTION_BACKSPACE = 110

MAXCAMS = 4

# Set plugin variables
__addon__        = xbmcaddon.Addon()
__addon_id__     = __addon__.getAddonInfo('id')
__addon_path__   = __addon__.getAddonInfo('path')
__profile__      = __addon__.getAddonInfo('profile')
__icon__         = os.path.join(__addon_path__, 'icon.png')
__loading__      = os.path.join(__addon_path__, 'loading.gif')

# Get settings
SETTINGS = {
    'width':         int(float(__addon__.getSetting('width'))),
    'height':        int(float(__addon__.getSetting('height'))),
    'interval':      int(float(__addon__.getSetting('interval'))),
    'autoClose':     bool(__addon__.getSetting('autoClose') == 'true'),
    'duration':      int(float(__addon__.getSetting('duration')) * 1000),
    'alignment':     int(float(__addon__.getSetting('alignment'))),
    'padding':       int(float(__addon__.getSetting('padding'))),
    'animate':       bool(__addon__.getSetting('animate') == 'true'),
    'aspectRatio':   int(float(__addon__.getSetting('aspectRatio')))
    }

CAMERAS          = []

streamid         = 0
streamurl        = None
streamusr        = None
streampwd        = None
streamwd         = 0
streamht         = 0

ffmpeg_exec      = 'ffmpeg.exe' if platform.system() == 'Windows' else 'ffmpeg'

if len(sys.argv) > 1:
    for i in range (1, len(sys.argv)):
        try:
            if sys.argv[i].split('=')[0] == 'streamid':
                streamid = int(sys.argv[i].split('=')[1])
                # break here, or keep on searching for other arguments
                #break
            if sys.argv[i].split('=')[0] == 'user':
                streamusr = sys.argv[i].split('=')[1]
            if sys.argv[i].split('=')[0] == 'password':
                streampwd = sys.argv[i].split('=')[1]
            if sys.argv[i].split('=')[0] == 'url':
                streamurl = sys.argv[i].split('=')[1]
            if sys.argv[i].split('=')[0] == 'width':
                streamwd = int(sys.argv[i].split('=')[1])
            if sys.argv[i].split('=')[0] == 'height':
                streamht = int(sys.argv[i].split('=')[1])
            if sys.argv[i].split('=')[0] == 'duration':
                SETTINGS['duration'] = int(sys.argv[i].split('=')[1])
        except:
            continue

if streamid in range(1, MAXCAMS + 1) and (streamurl or __addon__.getSetting('url{:d}'.format(streamid))):
    cam = {
        'url': streamurl or __addon__.getSetting('url{:d}'.format(streamid)),
        'username': streamusr or __addon__.getSetting('username{:d}'.format(streamid)),
        'password': streampwd or __addon__.getSetting('password{:d}'.format(streamid))
        }
    CAMERAS.append(cam)
    if streamwd > 0:    SETTINGS['width']  = streamwd
    if streamht > 0:    SETTINGS['height'] = streamht
else:
    for i in range(MAXCAMS):
        if __addon__.getSetting('active{:d}'.format(i + 1)) == 'true':
            cam = {
                'url':      __addon__.getSetting('url{:d}'.format(i + 1)),
                'username': __addon__.getSetting('username{:d}'.format(i + 1)),
                'password': __addon__.getSetting('password{:d}'.format(i + 1))
                }
            CAMERAS.append(cam)

# Utils
def log(message,loglevel=INFO):
    xbmc.log(msg='[{}] {}'.format(__addon_id__, message), level=loglevel)


def which(pgm):
    for path in os.getenv('PATH').split(os.path.pathsep):
        p = os.path.join(path, pgm)
        if os.path.exists(p) and os.access(p, os.X_OK):
            return p

    return None

# Classes
class CamPreviewDialog(xbmcgui.WindowDialog):
    def __init__(self, cameras):
        self.total = len(cameras)
        self.cams = cameras

        passwd_mgr = HTTPPasswordMgrWithDefaultRealm()
        self.opener = build_opener()

        for i in range(self.total):
            if self.cams[i]['username'] and self.cams[i]['password']:
                passwd_mgr.add_password(None, self.cams[i]['url'], self.cams[i]['username'], self.cams[i]['password'])
                self.opener.add_handler(HTTPBasicAuthHandler(passwd_mgr))
                self.opener.add_handler(HTTPDigestAuthHandler(passwd_mgr))

            randomname = ''.join([random.choice(string.ascii_letters + string.digits) for n in range(32)])
            self.cams[i]['tmpdir'] = os.path.join(__profile__, randomname)
            if not xbmcvfs.exists(self.cams[i]['tmpdir']):
                xbmcvfs.mkdir(self.cams[i]['tmpdir'])

            x, y, w, h = self.coordinates(i)
            self.cams[i]['control'] = xbmcgui.ControlImage(x, y, w, h, __loading__, aspectRatio = SETTINGS['aspectRatio'])
            self.addControl(self.cams[i]['control'])

            if SETTINGS['animate']:
                if SETTINGS['alignment'] in [0, 4, 6, 8, 9]:
                        direction = 1
                else:
                    direction = -1
                self.cams[i]['control'].setAnimations([('WindowOpen', 'effect=slide start=%d time=1000 tween=cubic easing=in'%(w*direction),), ('WindowClose', 'effect=slide end=%d time=1000 tween=cubic easing=in'%(w*direction),)])


    def coordinates(self, position):
        WIDTH  = 1280
        HEIGHT = 720

        w = SETTINGS['width']
        h = SETTINGS['height']
        p = SETTINGS['padding']

        alignment = SETTINGS['alignment']

        if alignment == 0: # vertical right, top to bottom
            x = int(WIDTH - (w + p))
            y = int(p + position * (h + p))
        if alignment == 1: # vertical left, top to bottom
            x = int(p)
            y = int(p + position * (h + p))
        if alignment == 2: # horizontal top, left to right
            x = int(p + position * (w + p))
            y = int(p)
        if alignment == 3: # horizontal bottom, left to right
            x = int(p + position * (w + p))
            y = int(HEIGHT - (h + p))
        if alignment == 4: # square right
            x = int(WIDTH - (2 - position%2) * (w + p))
            y = int(p + position/2 * (h + p))
        if alignment == 5: # square left
            x = int(p + position%2 * (w + p))
            y = int(p + position/2 * (h + p))
        if alignment == 6: # vertical right, bottom to top
            x = int(WIDTH - (w + p))
            y = int(HEIGHT - (position + 1) * (h + p))
        if alignment == 7: # vertical left, bottom to top
            x = int(p)
            y = int(HEIGHT - (position + 1) * (h + p))
        if alignment == 8: # horizontal top, right to left
            x = int(WIDTH - (position + 1) * (w + p))
            y = int(p)
        if alignment == 9: # horizontal bottom, right to left
            x = int(WIDTH - (position + 1) * (w + p))
            y = int(HEIGHT - (h + p))

        return x, y, w, h


    def start(self):
        self.show()
        self.isRunning = True

        for i in range(self.total):
            Thread(target=self.update, args=(self.cams[i],)).start()

        startTime = time.time()
        while(not SETTINGS['autoClose'] or (time.time() - startTime) * 1000 <= SETTINGS['duration']):
            if not self.isRunning:
                 break
            xbmc.sleep(500)

        self.isRunning = False

        self.close()
        self.cleanup()


    def update(self, cam):
        request = Request(cam['url'])
        index = 1

        type = cam['url'][:4]

        if type == 'rtsp':
            if not which(ffmpeg_exec):
                log('Error: {} not installed. Can\'t process rtsp input format.'.format(ffmpeg_exec))
                #self.isRunning = False
                self.stop()
                return

            if cam['username'] and cam['password']:
                input = 'rtsp://{}:{}@{}'.format(cam['username'], cam['password'], cam['url'][7:])
            else:
                input = cam['url']

            output = os.path.join(cam['tmpdir'], 'snapshot_%06d.jpg')
            command = [ffmpeg_exec,
                      '-nostdin',
                      '-rtsp_transport', 'tcp',
                      '-i', input,
                      '-an',
                      '-f', 'image2',
                      '-vf', 'fps=fps='+str(int(1000.0/SETTINGS['interval'])),
                      '-q:v', '10',
                      '-s', str(SETTINGS['width'])+'x'+str(SETTINGS['height']),
                      '-vcodec', 'mjpeg',
                      translatePath(output)]
            p = subprocess.Popen(command)

        while(self.isRunning):
            snapshot = os.path.join(cam['tmpdir'], 'snapshot_{:06d}.jpg'.format(index))
            index += 1

            try:
                if type == 'http':
                    imgData = self.opener.open(request).read()

                    if imgData:
                        file = xbmcvfs.File(snapshot, 'wb')
                        file.write(bytearray(imgData))
                        file.close()

                elif type == 'rtsp':
                    while(self.isRunning):
                        if xbmcvfs.exists(snapshot):
                            break
                        xbmc.sleep(10)

                elif xbmcvfs.exists(cam['url']):
                    xbmcvfs.copy(cam['url'], snapshot)

            except Exception as e:
                log(str(e))
                #snapshot = __loading__
                snapshot = None

            #if snapshot and xbmcvfs.exists(snapshot):
            if snapshot:
                cam['control'].setImage(snapshot, False)

            if type != 'rtsp':
                xbmc.sleep(SETTINGS['interval'])

        if type == 'rtsp' and p.pid:
            p.terminate()


    def cleanup(self):
        for i in range(self.total):
            files = xbmcvfs.listdir(self.cams[i]['tmpdir'])[1]
            for file in files:
                xbmcvfs.delete(os.path.join(self.cams[i]['tmpdir'], file))
            xbmcvfs.rmdir(self.cams[i]['tmpdir'])


    def onAction(self, action):
        if action in (ACTION_PREVIOUS_MENU, ACTION_STOP, ACTION_BACKSPACE, ACTION_NAV_BACK):
            self.stop()


    def stop(self):
        self.isRunning = False


if __name__ == '__main__':
    if streamid > 0:
        log('Addon called with streamid={}'.format(streamid))
        if streamurl:
            log('and url={}'.format(streamurl))

    camPreview = CamPreviewDialog(CAMERAS)
    camPreview.start()

    del camPreview
