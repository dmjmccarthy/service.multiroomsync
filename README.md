# Multi-Room Sync (Kodi Add-on)

Multi-room Sync is a plugin for [Kodi](https://www.kodi.tv) to allow multiple Kodi instances on the same network to playback the same video in synchronisation.

One Kodi instance must be designated the *master* instance from with playback is controlled by the user. The add-on will mirror playback on the *slave* devices.

> **This add-on does not stream video or audio between Kodi instances.** It is assumed that the media file is available to each system seperatly (eg. in the file system).

* Cross-platform - tested between Windows and Android devices.
* Local files are played back almost seemlessly in sync between Kodi instances.
* HTTP steams can be played back, but are not played back seemlessly in sync between devices. This is because I have not (yet) implimented an alternative procedure to reliably change the playback position in internet steams which doesn't result in buffering, which puts playback out of sync. 

## Setup

### Preliminaries

* Kodi instances communicate via Kodi's JSON-RPC API. Static IP addresses are preferred.

* Media files that are played by the *master* system must also be available to the *slave* system. By default they should be available at the same file path, but the 'common folder' option will redirect file paths to a different location. (This option is essential to manage different file systems in for cross-platform operation)

### Master Kodi Instance

1. This add-on must be installed in the master Kodi instance.

1. The add-on has no interface apart from the settings screen.

1. Enable the first client, and enter the IP address and port (default 8080), and credentials (default kodi:kodi). If using the common folder option, enter the file path on remote system. Forward/back slashes should be entered as the remote system will interpret them.

### Slave Kodi Instances

This plugin does not need to be installed on *slave* instances, and should be disabled if it is installed.

Kodi settings > Services > Control

* Allow remote control via HTTP = Yes
* (optional) modify username/password/port as required
* Allow remote control from applications on other systems = Yes

## TODO

* Adaptive high-latency management

* Improve seek accuracy