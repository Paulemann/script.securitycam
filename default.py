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

# Constants
ACTION_PREVIOUS_MENU = 10
ACTION_BACKSPACE = 110
ACTION_NAV_BACK = 92

MAXCAMS = 4

# Set plugin variables
__addon__        = xbmcaddon.Addon()
__addon_id__     = __addon__.getAddonInfo('id')
__addon_path__   = __addon__.getAddonInfo('path')
__profile__      = __addon__.getAddonInfo('profile')
__icon__         = os.path.join(__addon_path__, 'icon.png')
__loading__      = os.path.join(__addon_path__, 'loading.gif')

# Get settings
_width           = int(float(__addon__.getSetting('width')))
_height          = int(float(__addon__.getSetting('height')))
_interval        = int(float(__addon__.getSetting('interval')))
_autoClose       = bool(__addon__.getSetting('autoClose') == 'true')
_duration        = int(float(__addon__.getSetting('duration')) * 1000)
_alignment       = int(float(__addon__.getSetting('alignment')))
_padding         = int(float(__addon__.getSetting('padding')))
_animate         = bool(__addon__.getSetting('animate') == 'true')
_aspectRatio     = int(float(__addon__.getSetting('aspectRatio')))

active           = [False] * MAXCAMS

urls             = [None] * MAXCAMS
usernames        = [None] * MAXCAMS
passwords        = [None] * MAXCAMS

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
                _duration = int(sys.argv[i].split('=')[1])
        except:
            continue

if streamid in range(1, MAXCAMS + 1) and __addon__.getSetting('url{:d}'.format(streamid)):
    urls[0] = streamurl or __addon__.getSetting('url{:d}'.format(streamid))
    usernames[0] = streamusr or __addon__.getSetting('username{:d}'.format(streamid))
    passwords[0] = streampwd or __addon__.getSetting('password{:d}'.format(streamid))
    if streamwd > 0:
        _width  = streamwd
    if streamht > 0:
        _height = streamht
else:
    count = 0
    for i in range(MAXCAMS):
        active[i] = bool(__addon__.getSetting('active{:d}'.format(i + 1)) == 'true')
        if active[i]:
            urls[count] = __addon__.getSetting('url{:d}'.format(i + 1))
            usernames[count] = __addon__.getSetting('username{:d}'.format(i + 1))
            passwords[count] = __addon__.getSetting('password{:d}'.format(i + 1))
            count += 1

# Utils
def log(message,loglevel=xbmc.LOGNOTICE):
    xbmc.log(msg='[{}] {}'.format(__addon_id__, message), level=loglevel)

def which(pgm):
    for path in os.getenv('PATH').split(os.path.pathsep):
        p=os.path.join(path, pgm)
        if os.path.exists(p) and os.access(p, os.X_OK):
            return p

    return None

# Auth Scheme Mapping for Requets
AUTH_MAP = {
    'basic': HTTPBasicAuth,
    'digest': HTTPDigestAuth,
}

def auth_get(url, *args, **kwargs):
    r = requests.get(url, **kwargs)

    if r.status_code != 401:
        return r

    auth_scheme = r.headers['WWW-Authenticate'].split(' ')[0]
    auth = AUTH_MAP.get(auth_scheme.lower())

    if not auth:
        raise ValueError('Unknown authentication scheme')

    r = requests.get(url, auth=auth(*args), **kwargs)

    return r

# Classes
class CamPreviewDialog(xbmcgui.WindowDialog):
    def __init__(self, urls, usernames, passwords):
        self.cams = [{'url':None, 'username':None, 'password':None, 'tmpdir':None, 'control':None} for i in range(MAXCAMS)]

        passwd_mgr = HTTPPasswordMgrWithDefaultRealm()
        self.opener = build_opener()

        for i in range(MAXCAMS):
            if urls[i]:
                self.cams[i]['url'] = urls[i]

                if usernames[i] and passwords[i]:
                    self.cams[i]['username'] = usernames[i]
                    self.cams[i]['password'] = passwords[i]

                    passwd_mgr.add_password(None, self.cams[i]['url'], self.cams[i]['username'], self.cams[i]['password'])
                    self.opener.add_handler(HTTPBasicAuthHandler(passwd_mgr))
                    self.opener.add_handler(HTTPDigestAuthHandler(passwd_mgr))

                randomname = ''.join([random.choice(string.ascii_letters + string.digits) for n in range(32)])
                self.cams[i]['tmpdir'] = os.path.join(__profile__, randomname)
                if not xbmcvfs.exists(self.cams[i]['tmpdir']):
                    xbmcvfs.mkdir(self.cams[i]['tmpdir'])

                x, y, w, h = self.coordinates(i)
                self.cams[i]['control'] = xbmcgui.ControlImage(x, y, w, h, __loading__, aspectRatio = _aspectRatio)
                self.addControl(self.cams[i]['control'])

                if _animate:
                    if _alignment in [0, 4, 6, 8, 9]:
                        direction = 1
                    else:
                        direction = -1
                    self.cams[i]['control'].setAnimations([('WindowOpen', 'effect=slide start=%d time=1000 tween=cubic easing=in'%(w*direction),), ('WindowClose', 'effect=slide end=%d time=1000 tween=cubic easing=in'%(w*direction),)])

    def coordinates(self, position):
        COORD_GRID_WIDTH = 1280
        COORD_GRID_HEIGHT = 720

        scaledWidth = int(float(COORD_GRID_WIDTH) / self.getWidth() * _width)
        scaledHeight = int(float(COORD_GRID_HEIGHT) / self.getHeight() * _height)

        scaledPaddingX = int(float(COORD_GRID_WIDTH) / self.getWidth() * _padding)
        scaledPaddingY = int(float(COORD_GRID_HEIGHT) / self.getHeight() * _padding)

        if _alignment == 0: # vertical right, top to bottom
            scaledX = COORD_GRID_WIDTH - scaledWidth - scaledPaddingX
            scaledY = position * scaledHeight + (position + 1) * scaledPaddingY
        if _alignment == 1: # vertical left, top to bottom
            scaledX = scaledPaddingX
            scaledY = position * scaledHeight + (position + 1) * scaledPaddingY
        if _alignment == 2: # horizontal top, left to right
            scaledX = position * scaledWidth + (position + 1) * scaledPaddingX
            scaledY = scaledPaddingY
        if _alignment == 3: # horizontal bottom, left to right
            scaledX = position * scaledWidth + (position + 1) * scaledPaddingX
            scaledY = COORD_GRID_HEIGHT - scaledHeight - scaledPaddingY
        if _alignment == 4: # square right
            scaledX = COORD_GRID_WIDTH - (2 - position%2) * scaledWidth - (2 - position%2) * scaledPaddingX
            scaledY = position/2 * scaledHeight + (position/2 + 1) * scaledPaddingY
        if _alignment == 5: # square left
            scaledX = position%2 * scaledWidth + (position%2 + 1) * scaledPaddingX
            scaledY = position/2 * scaledHeight + (position/2 + 1) * scaledPaddingY
        if _alignment == 6: # vertical right, bottom to top
            scaledX = COORD_GRID_WIDTH - scaledWidth - scaledPaddingX
            scaledY = COORD_GRID_HEIGHT - (position + 1) * scaledHeight + (position + 1) * scaledPaddingY
        if _alignment == 7: # vertical left, bottom to top
            scaledX = scaledPaddingX
            scaledY = COORD_GRID_HEIGHT - (position + 1) * scaledHeight + (position + 1) * scaledPaddingY
        if _alignment == 8: # horizontal top, right to left
            scaledX = COORD_GRID_WIDTH - (position + 1) * scaledWidth - (position + 1) * scaledPaddingX
            scaledY = scaledPaddingY
        if _alignment == 9: # horizontal bottom, right to left
            scaledX = COORD_GRID_WIDTH - (position + 1) * scaledWidth - (position + 1) * scaledPaddingX
            scaledY = COORD_GRID_HEIGHT - scaledHeight - scaledPaddingY

        return scaledX, scaledY, scaledWidth, scaledHeight

    def start(self):
        self.show()
        self.isRunning = True

        for i in range(MAXCAMS):
            if self.cams[i]['url']:
                Thread(target=self.update, args=(self.cams[i],)).start()

        startTime = time.time()
        while(not _autoClose or (time.time() - startTime) * 1000 <= _duration):
            if not self.isRunning:
                 break

            xbmc.sleep(500)

        self.isRunning = False

        self.close()
        self.cleanup()

    def update(self, cam):
        request = Request(cam['url'])
        index = 1

        if cam['url'][:4] == 'rtsp' and not which(ffmpeg_exec):
            log('Error: {} not installed. Can\'t process rtsp input format.'.format(ffmpeg_exec))
            #self.isRunning = False
            self.stop()
            return

        if cam['url'][:4] == 'rtsp':
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
                      '-vf', 'fps=fps='+str(int(1000.0/_interval)),
                      '-q:v', '10',
                      '-s', str(_width)+'x'+str(_height),
                      '-vcodec', 'mjpeg',
                      xbmc.translatePath(output)]
            p = subprocess.Popen(command)

        while(self.isRunning):
            snapshot = os.path.join(cam['tmpdir'], 'snapshot_{:06d}.jpg'.format(index))
            index += 1

            try:
                if cam['url'][:4] == 'http':
                    imgData = self.opener.open(request).read()

                    #r = auth_get(cam['url'], cam['username'], cam['password'], verify=False, stream=True)
                    #if r.status_code == 200: # success!
                    #    imgData = r.content

                    if imgData:
                        file = xbmcvfs.File(snapshot, 'wb')
                        file.write(bytearray(imgData))
                        file.close()

                elif cam['url'][:4] == 'rtsp':
                    while(self.isRunning):
                       if xbmcvfs.exists(snapshot):
                           break

                elif xbmcvfs.exists(cam['url']):
                    xbmcvfs.copy(cam['url'], snapshot)

            except Exception as e:
                log(str(e))
                #snapshot = __loading__
                snapshot = None

            #if snapshot and xbmcvfs.exists(snapshot):
            if snapshot:
                cam['control'].setImage(snapshot, False)

            if cam['url'][:4] != 'rtsp' and which(ffmpeg_exec):
                xbmc.sleep(_interval)

        if cam['url'][:4] == 'rtsp' and p.pid:
            p.terminate()

    def cleanup(self):
        for i in range(MAXCAMS):
            if self.cams[i]['tmpdir']:
                files = xbmcvfs.listdir(self.cams[i]['tmpdir'])[1]
                for file in files:
                    xbmcvfs.delete(os.path.join(self.cams[i]['tmpdir'], file))
                xbmcvfs.rmdir(self.cams[i]['tmpdir'])

    #def onAction(self, action):
    #    if action in (ACTION_PREVIOUS_MENU, ACTION_BACKSPACE, ACTION_NAV_BACK):
    #        self.stop()
    #    #else:
    #    #    curWinID = xbmcgui.getCurrentWindowId()
    #    #    xbmc.executebuiltin('Action(%s,%s)' % (self.Action[action.getId()], curWinID))

    def stop(self):
        self.isRunning = False


if __name__ == '__main__':
    if streamid > 0:
        log('Addon called with streamid={}'.format(streamid))

    camPreview = CamPreviewDialog(urls, usernames, passwords)
    camPreview.start()

    del camPreview
