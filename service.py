# This file is part of Multi-Room Sync, a Kodi Add on
# Copyright (C) 2021  dmjmccarthy
# A fork of MediaMirror by Lunatixz (C) 2017 <https://github.com/Lunatixz/KODI_Addons/>

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import re, socket, json, copy, os, traceback, requests, datetime, time, random
import xbmc, xbmcgui, xbmcaddon, xbmcvfs

# Plugin Info
ADDON_ID = 'service.multiroomsync'
REAL_SETTINGS = xbmcaddon.Addon(id=ADDON_ID)
ADDON_NAME = REAL_SETTINGS.getAddonInfo('name')
ADDON_PATH = REAL_SETTINGS.getAddonInfo('path').decode('utf-8')
ADDON_VERSION = REAL_SETTINGS.getAddonInfo('version')
ICON = REAL_SETTINGS.getAddonInfo('icon')
DEBUG = REAL_SETTINGS.getSetting('enableDebug') == "true"

POLL = int(REAL_SETTINGS.getSetting('pollTIME'))
maximumDrift = int(REAL_SETTINGS.getSetting('maximumDrift'))
hostCommonPath = REAL_SETTINGS.getSetting('host_CommonPath')
maxNetworkLatency = datetime.timedelta(milliseconds=
    int(REAL_SETTINGS.getSetting('maxNetworkLatency')))
# If editing these, also edit onSettingsChange

networkLatencyHistoryCount = 20
adjustForNetworkLatency = False
seekOrDriftLimit = datetime.timedelta(milliseconds=4000) #milliseconds
skipChecksWhenInSync = 5
checksBeingSkipped = 0
httpMaximumDrift = 5000 #milliseconds
httpMediaPlaying = False
playbackStatusMessages = {
    0 : "Cannot communicate with client",
    1 : "The client is not playing the correct media",
    2 : "Client playback position is outside threshold - make seek correction",
    3 : "client playback position is outside threshold - make drift correction",
    4 : "client playback position is outside threshold - not yet making correction",
    5 : "Client playback position is good" 
}
socket.setdefaulttimeout(30)

def log(msg, level = xbmc.LOGDEBUG):
    if DEBUG == False and level != xbmc.LOGERROR:
        return
    elif level == xbmc.LOGERROR:
        msg += ' ,' + traceback.format_exc()
    xbmc.log(ADDON_ID + '-' + ADDON_VERSION + '-' + str(msg), level)

def ascii(string):
    if isinstance(string, basestring):
        if isinstance(string, unicode):
           string = string.encode('ascii', 'ignore')
    return string
    
def uni(string):
    if isinstance(string, basestring):
        if isinstance(string, unicode):
           string = string.encode('utf-8', 'ignore' )
        else:
           string = ascii(string)
    return string
     

def floor(x):
    x-= x%1
    return x

def mean(x):
    sumseconds = 0
    for delta in x:
        sumseconds += delta.total_seconds()
    mean = sumseconds / len(x) 
    return datetime.timedelta(seconds=mean)

def splitTimedeltaToUnits(seekTime):
    seek = str(seekTime)
    log('splitTimedeltaToUnits, seek = ' + seek)
    seek = seek.split(":")
    try:
        hours = int(seek[0])
    except:
        hours = 0
    try:
        minutes = int(seek[1])
    except:
        minutes = 0
    Mseconds = str(seek[2])
    seconds = int(Mseconds.split(".")[0])
    try:
        milliseconds = int(Mseconds.split(".")[1])
        milliseconds = int(str(milliseconds)[:3])
    except:
        milliseconds = 0
    return hours, minutes, seconds, milliseconds 

def driftHistoryToString(driftHistory):
    historyString = ""
    for epoch in driftHistory:
        historyString += ", " + str(epoch.total_seconds())
    return historyString

def sendLocal(command):
    data = ''
    try:
        data = xbmc.executeJSONRPC(uni(command))
    except UnicodeEncodeError:
        data = xbmc.executeJSONRPC(ascii(command))
    return uni(data)
    
def dumpJson(mydict, sortkey=True):
    #log("dumpJson")
    return json.dumps(mydict, sort_keys=sortkey)
    
def loadJson(string):
    #log("loadJson: len = " + str(len(string)))
    if len(string) == 0:
        return {}
    try:
        return json.loads(uni(string))
    except Exception as e:
        return json.loads(ascii(string))
        
def SendRemote(IPP, AUTH, CNUM, params, IPPprops):
    log('SendRemote: request IPP = ' + IPP + ', params = ' + json.dumps(params))
    try:
        xbmc_host, xbmc_port = IPP.split(":")
        username, password = AUTH.split(":")
        kodi_url = 'http://' + xbmc_host +  ':' + xbmc_port + '/jsonrpc'
        headers = {"Content-Type":"application/json"}
        time_before = time.time()
        response = requests.post(kodi_url,
                          data=json.dumps(params),
                          headers=headers,
                          auth=(username,password))
        log('SendRemote: response = ' + str(response.status_code) + ' ' + json.dumps(response.json()))
        #xbmc.sleep(10) #arbitrary sleep to avoid network flood, add to latency value.
        time_after = time.time() 
        time_taken = time_after-time_before
        latency = datetime.timedelta(seconds=round(time_taken,2))
        IPPprops["networkLatency"] = latency
        IPPprops["networkLatencyHistory"].append(latency)
        if len(IPPprops["networkLatencyHistory"]) > networkLatencyHistoryCount:
            IPPprops["networkLatencyHistory"].pop(0)
        return response.json()
    except Exception as e:
        log('SendRemote: exception ' + str(e.message))
        pass
    
def getActivePlayer():
    json_query = ('{"jsonrpc":"2.0","method":"Player.GetActivePlayers","params":{},"id":1}')
    json_response = loadJson(sendLocal(json_query))
    if json_response and 'result' in json_response:
        for response in json_response['result']:
            id = response.get('playerid','')
            if id:
                log("getActivePlayer, id = " + str(id)) 
                return id
    return 1

def clearSyncHistory(IPPlst):
    log('clearSyncHistory')
    for IPP in IPPlst:
        IPP[4]['syncIntervalsCount'] = 0
        IPP[4]['driftHistory'] = []
        IPP[4]['LostSyncIntervalsCount'] = 0
    return IPPlst

def decidePlaybackStatus(IPP):
    log('decidePlaybackStatus')
    #Playback status logic
    diff_playtime = IPP[4]['lastDrift']
    maxDrift = IPP[4]['maximumDrift']

    log('decidePlaybackStatus: maximumDrift = ' + str(maxDrift) + 's')
    log('decidePlaybackStatus: diff_playtime = ' + str(diff_playtime.total_seconds()) + 's')

    if abs(diff_playtime.total_seconds()) <= maxDrift:
        playbackStatus = 5
        IPP[4]['syncIntervalsCount'] += 1
        IPP[4]['LostSyncIntervalsCount'] = 0
    elif abs(diff_playtime.total_seconds()) <= abs(seekOrDriftLimit.total_seconds()):
        if (IPP[4]['LostSyncIntervalsCount'] < (IPP[4]['maxLostSyncIntervalsCount']-1)) and (IPP[4]['playbackStatus'] >=4):
            #log('decidePlaybackStatus: diff_playtime =' + str(diff_playtime.total_seconds()) +'s, seekOrDriftLimit =' + str(seekOrDriftLimit))
            playbackStatus = 4
            IPP[4]['LostSyncIntervalsCount'] += 1
        else:
            playbackStatus = 3
            IPP[4]['syncIntervalsCount'] += 0
    else:
        playbackStatus = 2
        IPP[4]['syncIntervalsCount'] += 0

    # Playback status messages
    if playbackStatus == 5:
        log("decidePlaybackStatus: Sync: IPP=" + IPP[0] + " OK for " + 
            str(IPP[4]['syncIntervalsCount']))
    elif playbackStatus == 4:
        log("decidePLaybackStatus: Sync: IPP=" + IPP[0] + " Starting to drift for " + str(IPP[4]["LostSyncIntervalsCount"]))
    elif playbackStatus == 3:
        log("decidePlaybackStatus: Sync: IPP=" + IPP[0] + " Correct now using drift")
    elif playbackStatus == 2:
        log("decidePlaybackStatus: Sync: IPP=" + IPP[0] + " Correct now using seek")
    #log('decidePlaybackStatus playbackStatus = ' + str(playbackStatus))
    log("decidePlaybackStatus: Sync: IPP=" + IPP[0] + ", history = " + 
        driftHistoryToString(IPP[4]['driftHistory']))
    IPP[4]['playbackStatus'] = playbackStatus

    return IPP

class Player(xbmc.Player):
    def __init__(self):
        xbmc.Player.__init__(self, xbmc.Player())
        
        
    def onPlayBackStarted(self):
        log('onPlayBackStarted')
        #collect detailed player info
        self.playType, self.playLabel, self.playFile, self.playThumb = self.getPlayerItem()
        #some client screensavers do not respect onplay, but do respect onstop. send stop to close screensaver before playback.
        #if self.stopClient(self.Service.Monitor.IPPlst) == True:
            #self.playClient(self.Service.Monitor.IPPlst)
        self.playClient(self.Service.Monitor.IPPlst)
        
        
    def onPlayBackEnded(self):
        log('onPlayBackEnded')
            
        
    def onPlayBackStopped(self):
        log('onPlayBackStopped')
        self.stopClient(self.Service.Monitor.IPPlst)
        
        
    def onPlayBackPaused(self):
        log('onPlayBackPaused')
        self.pauseClient(self.Service.Monitor.IPPlst)

        
    def onPlayBackResumed(self):
        log('onPlayBackResumed')
        self.resumeClient(self.Service.Monitor.IPPlst)
        
        
    def onPlayBackSpeedChanged(self):
        log('onPlayBackSpeedChanged')
        self.playClient(self.Service.Monitor.IPPlst)
        
        
    def onPlayBackSeekChapter(self):
        log('onPlayBackSeekChapter')
        self.playClient(self.Service.Monitor.IPPlst)
        
        
    def onPlayBackSeek(self, time, seekOffset):
        log('onPlayBackSeek')
        clearSyncHistory(self.Service.Monitor.IPPlst)
        self.playClient(self.Service.Monitor.IPPlst)

        
    def getPlayerFile(self):
        log('getPlayerFile')
        try:
            return (self.getPlayingFile().replace("\\\\","\\"))
        except:
            return ''
            
    def getPlayerTime(self):
        log('getPlayerTime')
        try:
            return self.getTime()
        except:
            return 0
              
    def getPlayerLabel(self):
        #log('getPlayerLabel')

        #find current activeplayer
        try:
            activeplayerid = getActivePlayer()
        except:
            return ''

        params = ({"jsonrpc":"2.0","id":1,"method":"Player.GetItem","params":{"playerid":activeplayerid,"properties":["title"]}})
        response = sendLocal(json.dumps(params))
        json_response = json.loads(response)

        return json_response['result']['item']['label']

    def getPlayerItem(self):
        json_query = ('{"jsonrpc":"2.0","method":"Player.GetItem","params":{"playerid":%d,"properties":["file","title","thumbnail","showtitle"]},"id":1}'%getActivePlayer())
        json_response = loadJson(sendLocal(json_query))
        if json_response and 'result' in json_response and 'item' in json_response['result']:
            type = json_response['result']['item']['type']
            if type == 'movie':
                label = json_response['result']['item']['label']
            else:
                label = (json_response['result']['item'].get('showtitle','') or json_response['result']['item']['label']) + ' - ' + json_response['result']['item']['title']
            if type == 'channel':
                file = json_response['result']['item']['id']
            else:
                file = json_response['result']['item'].get('file','')
            thumb = (json_response['result']['item']['thumbnail'] or ICON)
            return type, label, file, thumb
        return 'video', self.getPlayerLabel(), self.getPlayerFile(), ICON

    def getClientPVRid(self, IPP, label, id):
        log('getClientPVRid')      
        idLST = []
        for item in IPP[4]:
            log('getClientPVRid, %s =?= %s'%label, item['label'])
            if label == item['label']:
                log('getClientPVRid, found %s'%item['channelid'])
                #allow for duplicates, ex. multi-tuners on same PVR backend. 
                idLST.append(item['channelid'])
            if len(idLst) > 0:
                return random.choice(idLST)
        return id #return host id, maybe get a lucky match
                
    def sendClientInfo(self, IPPlst, label, thumb):
        log('sendClientInfo')
        params = ({"jsonrpc": "2.0", "method": "GUI.ShowNotification", "params": {"title":"Now Playing","message":label,"image":thumb}})
        seekValue = self.getPlayerTime()
        for IPP in IPPlst:
            SendRemote(IPP[0], IPP[1], IPP[3], params, IPP[4])
        return True

    def playClient(self, IPPlst):
        global httpMediaPlaying
        #log('playClient')
        #log('playClient : no in list = ' + str(len(IPPlst))) 
        #xbmc.executebuiltin("Notification('Media Mirror','playClient " + str(len(IPPlst)) + " devices')")
        if hasattr(self, 'playLabel'):
            label = self.playLabel
        else: label = None
        if hasattr(self, 'playThumb'):
            thumb = self.playThumb
        else: thumb = None
        #print(self.playType, self.playLabel, self.playFile, self.playThumb)
        localPlayFile = self.getPlayerFile()
        if "http" in localPlayFile[0:4]:
            httpMediaPlaying = True
        else:
            httpMediaPlaying = False

        for IPP in IPPlst:
            playFile = localPlayFile
            if hostCommonPath <> "" and IPP[4]["commonPath"] <> "":
                log("playClient, hostCommonPath = " + hostCommonPath + " commonPath = " + IPP[4]["commonPath"])
                playFile = playFile.replace(hostCommonPath, IPP[4]["commonPath"])
                if "/" in IPP[4]["commonPath"]: # Unix client
                    playFile = playFile.replace("\\","/")
                if "\\" in IPP[4]["commonPath"]: #Windows client
                    playFile = playFile.replace("/","\\")
            if type == 'channel':
                params = ({"jsonrpc": "2.0", "method": "Player.Open", "params": {"item": {"channelid": self.getClientPVRid(IPP, self.playLabel.split(' - ')[0], self.playFile)}}})
            elif self.getPlayerTime() > 0:
                seekTime = datetime.timedelta(seconds=self.getPlayerTime())
                seekTime += IPP[4]["offset"] #add user offset
                #todo netlatency
                
                hours, minutes, seconds, milliseconds = splitTimedeltaToUnits(seekTime)

                seek = str(seekTime)
                log('playClient, seek = ' + str(seekTime) + ' offset = ' + 
                    str(IPP[4]["offset"]))

                params = ({"jsonrpc": "2.0", "method": "Player.Open", "params": {"item": {"file": playFile},"options":{"resume":{"hours":hours,"minutes":minutes,"seconds":seconds ,"milliseconds":int(milliseconds)}}}})
                
            else:
                params = ({"jsonrpc": "2.0", "method": "Player.Open", "params": {"item": {"file": playFile}}})
            SendRemote(IPP[0], IPP[1], IPP[3], params, IPP[4])
        self.sendClientInfo(IPPlst, label, thumb)
        return True
    
    def seekClient(self, IPPlst):
        #log('seekClient')
        log('seekClient ' + str(len(IPPlst)) + ' in list')
        for IPP in IPPlst:
            seekTime = datetime.timedelta(seconds=self.getPlayerTime())
            seekTime += IPP[4]["offset"] #add user offset
            if adjustForNetworkLatency:
                seekTime -= (mean(IPP[4]["networkLatencyHistory"])/2)

            hours, minutes, seconds, milliseconds = splitTimedeltaToUnits(seekTime)

            if ( hours + minutes + seconds == 0) and (miliseconds <= seekOrDriftLimit):
                tweakclient(self)
                continue

            seek = str(seekTime)
            log('seekClient, seek = ' + str(seekTime) + ' offset = ' + 
                str(IPP[4]["offset"]))
            params = ({"jsonrpc": "2.0", "method": "Player.Seek", "params": {"value": {"hours":hours,"minutes":minutes,"seconds":seconds ,"milliseconds":int(milliseconds)}, "playerid":1}})
            SendRemote(IPP[0], IPP[1], IPP[3], params, IPP[4])
        return

    def slowClient(self, IPP):
        log('slowClient')
        sleepSeconds = IPP[4]["lastDrift"].total_seconds()
        log('slowClient: were going to pause for ' + str(sleepSeconds) + 's')
        #params = ({"jsonrpc": "2.0", "method": "Player.SetSpeed", "params": {"speed":0,"playerid":1}})
        params = ({"jsonrpc": "2.0", "method": "Player.PlayPause", "params": {"play":False,"playerid":1}})
        time_before = time.time()
        SendRemote(IPP[0], IPP[1], IPP[3], params, IPP[4])
        time_after = time.time() 
        time_taken = round(time_after-time_before,3)
        time.sleep(max((sleepSeconds - time_taken),0))
        #params = ({"jsonrpc": "2.0", "method": "Player.SetSpeed", "params": {"speed":1,"playerid":1}})
        params = ({"jsonrpc": "2.0", "method": "Player.PlayPause", "params": {"play":True,"playerid":1}})
        SendRemote(IPP[0], IPP[1], IPP[3], params, IPP[4])

    def speedClient(self, IPP):
        log('speedClient')
        sleepSeconds = -1 * IPP[4]["lastDrift"].total_seconds()
        log('speedClient: were going to play 2x for ' + str(sleepSeconds) + 's')
        params = ({"jsonrpc": "2.0", "method": "Player.SetSpeed", "params": {"speed":2,"playerid":1}})
        time_before = time.time()
        SendRemote(IPP[0], IPP[1], IPP[3], params, IPP[4])
        time_after = time.time() 
        time_taken = max(round(time_after-time_before,3),0)
        time.sleep(max((sleepSeconds - time_taken),0))
        params = ({"jsonrpc": "2.0", "method": "Player.SetSpeed", "params": {"speed":1,"playerid":1}})
        SendRemote(IPP[0], IPP[1], IPP[3], params, IPP[4])

    def driftClient(self, IPPlst):
        log('driftClient ' + str(len(IPPlst)) + ' in list')
        for IPP in IPPlst:
            if IPP[4]["lastDrift"].total_seconds() >= 0:
                self.slowClient(IPP)
            else:
                self.speedClient(IPP)
        return

    def stopClient(self, IPPlst):
        log('stopClient')
        params = ({"jsonrpc":"2.0","id":1,"method":"Player.Stop","params":{"playerid":1}})       
        for IPP in IPPlst: 
            SendRemote(IPP[0], IPP[1], IPP[3], params, IPP[4])
        return True
        
    def pauseClient(self, IPPlst):
        log('pauseClient')
        #params = ({"jsonrpc":"2.0","id":1,"method":"Player.Speed","params":{"speed":0}})
        params = ({"jsonrpc":"2.0","id":1,"method":"Input.ExecuteAction","params":{"action":"pause"}})
        for IPP in IPPlst: 
            SendRemote(IPP[0], IPP[1], IPP[3], params, IPP[4])
        return True
        
    def resumeClient(self, IPPlst):
        log('resumeClient')
        params = ({"jsonrpc":"2.0","id":1,"method":"Input.ExecuteAction","params":{"action":"play"}})       
        for IPP in IPPlst: 
            SendRemote(IPP[0], IPP[1], IPP[3], params, IPP[4])
        return True
        
    def playlistClient(self, IPPlst, file):
        log('PlaylistUPNP')
        params = ({"jsonrpc":"2.0","id":1,"method":"Player.Open","params":{"item": {"file": file}}})
        for IPP in IPPlst: 
            SendRemote(IPP[0], IPP[1], IPP[3], params, IPP[4])
        return True
             

class Monitor(xbmc.Monitor):
    def __init__(self):
        xbmc.Monitor.__init__(self, xbmc.Monitor())
        self.IPPlst = []
      
    def onSettingsChanged(self):
        log("onSettingsChanged")
        DEBUG = REAL_SETTINGS.getSetting('enableDebug') == "true"
        hostCommonPath = REAL_SETTINGS.getSetting('host_CommonPath')
        maxNetworkLatency = datetime.timedelta(milliseconds=
            int(REAL_SETTINGS.getSetting('maxNetworkLatency')))
        self.initClients()
        
    def initClients(self):
        log('initClients')
        self.IPPlst = []
        for i in range(1,5):
            if REAL_SETTINGS.getSetting("Client%d"%i) == "true":
                IPP = [REAL_SETTINGS.getSetting("Client%d_IPP"%i),REAL_SETTINGS.getSetting("Client%d_UPW"%i),0,i,
                {"networkLatency":datetime.timedelta(),
                "offset":datetime.timedelta(),
                "lastDrift":datetime.timedelta(),
                "maximumDrift":(maximumDrift/float(1000)), #seconds
                "maximumHttpDrift":(httpMaximumDrift/float(1000)), #seconds
                "commonPath":REAL_SETTINGS.getSetting("Client%d_CommonPath"%i),
                "syncIntervalsCount":0,
                "LostSyncIntervalsCount":0,
                "maxLostSyncIntervalsCount":int(REAL_SETTINGS.getSetting("maxLostSyncIntervals")),
                "driftHistory":[],
                "networkLatencyHistory":[], 
                "maxNetworkLatency":maxNetworkLatency,
                "playbackStatus":0}]
                self.IPPlst.append(IPP + [self.initClientPVR(IPP)])
        log('initClients, IPPlst = ' + str(self.IPPlst))
        
    def initClientPVR(self, IPP):
        log('initClientPVR')
        # params = ({"jsonrpc":"2.0","method":"PVR.GetChannels","params":{"channelgroupid":"alltv"},"id":1})
        # json_response = SendRemote(IPP[0], IPP[1], IPP[3], params)
        # if json_response and 'result' in json_response and 'channels' in json_response['result']:
        #     return json_response['result']['channels']
        return {}
        

class Service():
    global checksBeingSkipped

    def __init__(self):
        self.Player = Player()
        self.Monitor = Monitor()
        self.Player.Service  = self
        self.start()
 
 
    def chkClients(self):
        log('chkClients')
        log('chkClients START')
        
        failedLst = []
        seekLst = []
        driftLst = []

        #check if clients are playing the same content, ie "insync", return "outofsync" clients.
        for IPPlst in self.Monitor.IPPlst:

            #find current activeplayer
            params = ({"jsonrpc":"2.0","id":1,"method":"Player.GetActivePlayers"})
            
            json_response1 = SendRemote(IPPlst[0], IPPlst[1], IPPlst[3], params, IPPlst[4])
            try:
                activeplayerid = json_response1['result'][0]['playerid']
            except:
                log("chkClients, No ActivePlayer")
                failedLst.append(IPPlst)
                continue

            params = ({"jsonrpc":"2.0","id":1,"method":"Player.GetItem","params":{"playerid":activeplayerid,"properties":["title"]}})
            json_response = SendRemote(IPPlst[0], IPPlst[1], IPPlst[3], params, IPPlst[4])

            # get remote playback position
            params = ({"jsonrpc":"2.0","id":1,"method":"Player.GetProperties","params":{"playerid":activeplayerid,"properties":["time"]}})
            json_response2 = SendRemote(IPPlst[0], IPPlst[1], IPPlst[3], params, IPPlst[4])
            remote_playtime = datetime.timedelta(hours=json_response2["result"]["time"]["hours"],
                minutes=json_response2["result"]["time"]["minutes"],
                seconds=json_response2["result"]["time"]["seconds"],
                milliseconds=json_response2["result"]["time"]["milliseconds"] )
            log("remote playtime: " + str(remote_playtime))
            #check net latency
            log("network latency: " + str(IPPlst[4]["networkLatency"]))
            if IPPlst[4]['networkLatency'] > IPPlst[4] ["maxNetworkLatency"] :
                log("networkLatency over limit")
                continue
            # get local playback position
            local_playtime = datetime.timedelta(seconds=self.Player.getPlayerTime())
            log("local playtime: " + str(local_playtime))

            log("playback diff: " + str((remote_playtime - local_playtime).total_seconds()) + "s (ignoring network latency)")
            diff_playtime = remote_playtime - local_playtime
            if adjustForNetworkLatency:
                diff_playtime -= IPPlst[4]["networkLatency"]
            log("playback diff: " + str(diff_playtime.total_seconds()) + "s (allowing for network latency)")

            log("chkClients, IPP = " + str(IPPlst[0]) + " JSON =" + json.dumps(json_response)) 

            if json_response is None:
                failedLst.append(IPPlst)
                log("chkClients END, json_response is None")
                continue                
            
            if not json_response or 'result' not in json_response or 'item' not in json_response['result']:
                failedLst.append(IPPlst)
                log("chkClients END, json_response doesnt contain label")
                continue

            #there is a response
            if 'file' in json_response['result']['item']:
                clientFile  = json_response['result']['item']['file']
                log("chkClients, clientFile = " + clientFile) 
                localFile = self.Player.getPlayerFile()  
                log("chkClients, localFile = " + localFile)    
                if clientFile != self.Player.getPlayerFile():
                    failedLst.append(IPPlst)
                    log('chkClients END incorrect file')
                    continue
            else:
                #not all items contain a file, ex. pvr, playlists. so check title.
                clientLabel = json_response['result']['item']['label']
                log("chkClients, clientLabel = " + clientLabel) 
                localLabel = self.Player.getPlayerLabel()
                log("chkClients, localLabel = " + localLabel) 
                if clientLabel != self.Player.getPlayerLabel():
                    failedLst.append(IPPlst)
                    log('chkClients END incorrect label')
                    continue
            
            IPPlst[4]['lastDrift'] = diff_playtime
            offset = IPPlst[4]['offset']
            offset -= diff_playtime
            IPPlst[4]['offset'] = offset
            #IPPlst[4]['offset'] = IPPlst[4]['lastDrift']
            IPPlst[4]['driftHistory'].append(diff_playtime)

            IPPlst = decidePlaybackStatus(IPPlst)
            log('chkClients: playbackStatus = ' + str(IPPlst[4]["playbackStatus"]))
            if IPPlst[4]['playbackStatus'] == 3:
                driftLst.append(IPPlst)
            elif IPPlst[4]['playbackStatus'] == 2:
                seekLst.append(IPPlst)

        log('chkClients END')
        return failedLst, seekLst, driftLst

    def start(self):
        global checksBeingSkipped
        self.Monitor.initClients()
        while not self.Monitor.abortRequested():
            if self.Player.isPlayingVideo() == True and len(self.Monitor.IPPlst) > 0:
                #if xbmcgui.Window(10000).getProperty("PseudoTVRunning") == "True": 
                    #self.Monitor.waitForAbort(POLL)
                    #continue 
                if httpMediaPlaying == True:
                    log('start: httpMediaPlaying = True')
                elif checksBeingSkipped > 0:
                    log('start: skipping this check where all clients are in sync')
                    log('start: checksBeingSkipper = ' + str(checksBeingSkipped))
                    checksBeingSkipped =- 1
                else:
                    playLst, seekLst, driftLst = self.chkClients()
                    self.Player.playClient(playLst)
                    self.Player.seekClient(seekLst)
                    self.Player.driftClient(driftLst)
                    if len(playLst) + len(seekLst) + len(driftLst) == 0:
                        checksBeingSkipped = skipChecksWhenInSync
                        log('start: checksBeingSkipper = ' + str(checksBeingSkipped))
            if self.Monitor.waitForAbort(POLL):
                break
        self.Player.stopClient(self.Monitor.IPPlst)
Service()
