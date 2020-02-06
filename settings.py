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

import xbmcaddon

# Plugin Info
ADDON_ID = 'service.multiroomsync'
REAL_SETTINGS = xbmcaddon.Addon(id=ADDON_ID)
REAL_SETTINGS.openSettings() 