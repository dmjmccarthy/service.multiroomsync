# This file is part of Multi-Room Sync, a Kodi Add on
# Copyright (C) 2020  dmjmccarthy
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

def sendLocal(command):
    data = ''
    try:
        data = xbmc.executeJSONRPC(uni(command))
    except UnicodeEncodeError:
        data = xbmc.executeJSONRPC(ascii(command))
    return uni(data)
    
def dumpJson(mydict, sortkey=True):
    log("dumpJson")
    return json.dumps(mydict, sort_keys=sortkey)
    
def loadJson(string):
    log("loadJson: len = " + str(len(string)))
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
        xbmc.sleep(10) #arbitrary sleep to avoid network flood, add to latency value.
        time_after = time.time() 
        time_taken = time_after-time_before
        IPPprops["networkLatency"] = datetime.timedelta(seconds=round(time_taken,2))
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
        IPP[4]['syncEpochsCount'] = 0
        IPP[4]['driftHistory'] = []
        IPP[4]['initialSyncAchieved'] = 0
        IPP[4]['LostSyncEpochsCount'] = 0

  
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
        log('getPlayerLabel')

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
        #log('playClient')
        log('playClient : no in list = ' + str(len(IPPlst))) 
        #xbmc.executebuiltin("Notification('Media Mirror','playClient " + str(len(IPPlst)) + " devices')")
        if hasattr(self, 'playLabel'):
            label = self.playLabel
        else: label = None
        if hasattr(self, 'playThumb'):
            thumb = self.playThumb
        else: thumb = None
        #print(self.playType, self.playLabel, self.playFile, self.playThumb)
        localPlayFile = "/storage/emulated/0/Download/BigBuckBunny.mp4"
        localPlayFile = self.getPlayerFile()
        for IPP in IPPlst:
            if hostCommonPath <> "" and IPP[4]["commonPath"] <> "":
                playFile = localPlayFile
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
        log('seekClient')
        #xbmc.executebuiltin("Notification('Media Mirror','seekClient " + str(len(IPPlst)) + " devices')")
        for IPP in IPPlst:
            seekTime = datetime.timedelta(seconds=self.getPlayerTime())
            seekTime += IPP[4]["offset"] #add user offset
            hours, minutes, seconds, milliseconds = splitTimedeltaToUnits(seekTime)

            seek = str(seekTime)
            log('seekClient, seek = ' + str(seekTime) + ' offset = ' + 
                str(IPP[4]["offset"]))
            params = ({"jsonrpc": "2.0", "method": "Player.Seek", "params": {"value": {"hours":hours,"minutes":minutes,"seconds":seconds ,"milliseconds":int(milliseconds)}, "playerid":1}})
            SendRemote(IPP[0], IPP[1], IPP[3], params, IPP[4])
        return

    def stopClient(self, IPPlst):
        log('stopClient')
        params = ({"jsonrpc":"2.0","id":1,"method":"Player.Stop","params":{"playerid":1}})       
        for IPP in IPPlst: 
            SendRemote(IPP[0], IPP[1], IPP[3], params, IPP[4])
        return True
        
        
    def pauseClient(self, IPPlst):
        log('pauseClient')
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
        POLL  = int(REAL_SETTINGS.getSetting('pollTIME'))
        maximumDrift = int(REAL_SETTINGS.getSetting('maximumDrift'))
        #self.initClients()
        
        
    def initClients(self):
        log('initClients')
        self.IPPlst = []
        for i in range(1,6):
            if REAL_SETTINGS.getSetting("Client%d"%i) == "true":
                IPP = [REAL_SETTINGS.getSetting("Client%d_IPP"%i),REAL_SETTINGS.getSetting("Client%d_UPW"%i),0,i,
                {"networkLatency":datetime.timedelta(),
                "offset":datetime.timedelta(),
                "lastDrift":datetime.timedelta(),
                "maximumDrift":datetime.timedelta(milliseconds=maximumDrift),
                "commonPath":REAL_SETTINGS.getSetting("Client%d_CommonPath"%i),
                "syncEpochsCount":0,
                "LostSyncEpochsCount":0,
                "maxLostSyncEpochsCount":int(REAL_SETTINGS.getSetting("maxLostSyncEpochs")),
                "driftHistory":[],
                "initialSyncAchieved":False}]
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
    def __init__(self):
        self.Player = Player()
        self.Monitor = Monitor()
        self.Player.Service  = self
        self.start()
 
 
    def chkClients(self):
        log('chkClients')
        
        #check if clients are playing the same content, ie "insync", return "outofsync" clients.
        failedLst = []
        seekLst = []
        for IPPlst in self.Monitor.IPPlst:
            if xbmcgui.Window(10000).getProperty("PseudoTVRunning") == "True": 
                return []
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
            # get local playback position
            local_playtime = datetime.timedelta(seconds=self.Player.getPlayerTime())
            log("local playtime: " + str(local_playtime))
            log("network latency: " + str(IPPlst[4]["networkLatency"]))
            diff_playtime = remote_playtime - local_playtime - IPPlst[4]["networkLatency"]
            log("playback diff: " + str(diff_playtime) + "(allowing for network latency)")

            log("chkClients, IPP = " + str(IPPlst[0]) + " JSON =" + json.dumps(json_response)) 

            if json_response is None:
                failedLst.append(IPPlst)
                log("chkClients, json_response is None")
                continue                
            
            if not json_response or 'result' not in json_response or 'item' not in json_response['result']:
                failedLst.append(IPPlst)
                log("chkClients, json_response doesnt contain label")
                continue

            #there is a response
                
            if 'file' in json_response['result']['item']:
                clientFile  = json_response['result']['item']['file']
                log("chkClients, clientFile = " + clientFile) 
                localFile = self.Player.getPlayerFile()  
                log("chkClients, localFile = " + localFile)    
                if clientFile != self.Player.getPlayerFile():
                    failedLst.append(IPPlst)
                    continue
            else:
                #not all items contain a file, ex. pvr, playlists. so check title.
                clientLabel = json_response['result']['item']['label']
                log("chkClients, clientLabel = " + clientLabel) 
                localLabel = self.Player.getPlayerLabel()
                log("chkClients, localLabel = " + localLabel) 
                if clientLabel != self.Player.getPlayerLabel():
                    failedLst.append(IPPlst)
                    continue

            # If we've got this far, the client is playing the right media

            if not IPPlst[4]['initialSyncAchieved']:
                if abs(diff_playtime) > IPPlst[4]['maximumDrift']:
                #if abs(diff_playtime) > datetime.timedelta(microseconds=(IPPlst[4]['maximumDrift'].microseconds*0.5)):
                    log("chkClients: Sync: IPP=" + IPPlst[0] + " No inital sync yet")
                    IPPlst[4]['lastDrift'] = diff_playtime
                    offset = IPPlst[4]['offset']
                    newOffset = offset - diff_playtime
                    IPPlst[4]['offset'] = newOffset
                    seekLst.append(IPPlst)
                else:
                    log("chkClients: Sync: IPP=" + IPPlst[0] + " Inital sync")
                    # in sync the first time
                    IPPlst[4]['initialSyncAchieved'] = True
                    IPPlst[4]['syncEpochsCount'] = 1
                    IPPlst[4]['driftHistory'] = []
                    IPPlst[4]['driftHistory'].append(diff_playtime)
                continue
            
            # If we've got this far, we at least started playing in sync

            if abs(diff_playtime) <= IPPlst[4]['maximumDrift']:
                log("chkClients: Sync: IPP=" + IPPlst[0] + " OK for " + 
                    str(IPPlst[4]['syncEpochsCount']+1))
                IPPlst[4]['syncEpochsCount'] += 1
                IPPlst[4]['driftHistory'].append(diff_playtime)
                IPPlst[4]['LostSyncEpochsCount'] = 0
            else:
                if IPPlst[4]['LostSyncEpochsCount'] < (IPPlst[4]['maxLostSyncEpochsCount']-1):
                    log("chkClients: Sync: IPP=" + IPPlst[0] + " Not in sync")
                    IPPlst[4]['LostSyncEpochsCount'] += 1
                    IPPlst[4]['driftHistory'].append(diff_playtime)
                    continue
                
                historyString = ""
                for epoch in IPPlst[4]['driftHistory']:
                    historyString += ", " + str(epoch.total_seconds())
                historyString += ", [" + str(diff_playtime.total_seconds()) + "]"
                log("chkClients: Sync: IPP=" + IPPlst[0] + " Limit exceeded, history = " + historyString)
                #IPPlst[4]['driftHistory'] = []

                # we'll re sync
                IPPlstlst = []
                IPPlstlst.append(IPPlst)
                clearSyncHistory(IPPlstlst)

                #IPPlst[4]['offset'] += 
                seekLst.append(IPPlst)
                #IPPlst[4]['syncEpochsCount'] = 0



        return failedLst, seekLst
        

    def start(self):
        self.Monitor.initClients()
        while not self.Monitor.abortRequested():
            if self.Player.isPlayingVideo() == True and len(self.Monitor.IPPlst) > 0:
                if xbmcgui.Window(10000).getProperty("PseudoTVRunning") == "True": 
                    self.Monitor.waitForAbort(POLL)
                    continue 
                playLst, seekLst = self.chkClients()
                self.Player.playClient(playLst)
                self.Player.seekClient(seekLst)
            if self.Monitor.waitForAbort(POLL):
                break
        self.Player.stopClient(self.Monitor.IPPlst)
Service()
