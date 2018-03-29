# -*- coding: utf-8 -*-
"""
/***************************************************************************
 GVDigitizingTools
                                 A QGIS plugin
 Custom tools for digitizing
                             -------------------
        begin                : 2014-05-21
        copyright            : (C) 2014 by Guilhem Vellut
        email                : guilhem.vellut@gmail.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

def classFactory(iface):
    from gvdigitizingtools import GVDigitizingTools
    return GVDigitizingTools(iface)
