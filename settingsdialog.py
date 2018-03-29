# -*- coding: utf-8 -*-
"""
/***************************************************************************
 GVDigitizingToolsDialog
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

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *

import resources_rc
from settingsdialog_ui import Ui_Settings

import constants

class SettingsDialog(QDialog, Ui_Settings):
    def __init__(self):
        QDialog.__init__(self)
        self.setupUi(self)
        
    def clear(self):
        # settings are initialiwed when the plugin is initialiwed (when QGIS is open)
        settings = QSettings()
        angle = settings.value(constants.ARC_ANGLE, 0, type=float)
        self.lineEditArcAngle.setText(str(angle))
        numberOfPoints = settings.value(constants.ARC_NUMBEROFPOINTS,0,type=int)
        self.lineEditArcNumberOfPoints.setText(str(numberOfPoints))
        method = settings.value(constants.ARC_METHOD, "")
        if method == constants.ARC_METHOD_ANGLE:
            self.radioButtonAngle.setChecked(True)
        else:
            self.radioButtonNumberOfPoints.setChecked(True)
            
        enablePreview=settings.value(constants.PREVIEW_ENABLED, type=bool)
        self.checkBoxEnablePreview.setChecked(enablePreview)
        enableLimitPreview=settings.value(constants.PREVIEW_LIMIT_ENABLED, type=bool)
        self.checkBoxEnableLimitPreview.setChecked(enableLimitPreview)
        maxLimitPreview=settings.value(constants.PREVIEW_LIMIT_MAX, type=int)
        self.lineEditLimitPreviewGeometries.setText(str(maxLimitPreview))

    def accept(self):
        result, message, details = self.validate()
        if result:
            # save into QSettings
            settings = QSettings()
            # process arc settings
            isAngle = self.radioButtonAngle.isChecked()
            if isAngle:
                settings.setValue(constants.ARC_METHOD, constants.ARC_METHOD_ANGLE)
                angle = float(self.lineEditArcAngle.text())
                settings.setValue(constants.ARC_ANGLE, angle)
            else:
                settings.setValue(constants.ARC_METHOD, constants.ARC_METHOD_NUMBEROFPOINTS)
                numberOfPoints = int(self.lineEditArcNumberOfPoints.text())
                settings.setValue(constants.ARC_NUMBEROFPOINTS, numberOfPoints)
            
            isEnablePreview=self.checkBoxEnablePreview.isChecked()
            settings.setValue(constants.PREVIEW_ENABLED, isEnablePreview)
            isEnableLimitPreview=self.checkBoxEnableLimitPreview.isChecked()
            settings.setValue(constants.PREVIEW_LIMIT_ENABLED, isEnableLimitPreview)
            maxLimitPreview=int(self.lineEditLimitPreviewGeometries.text())
            settings.setValue(constants.PREVIEW_LIMIT_MAX, maxLimitPreview)
                
            self.done(QDialog.Accepted)
        else:
            msgBox = QMessageBox()
            msgBox.setWindowTitle(u"Error")
            msgBox.setText(message)
            msgBox.setInformativeText(details)
            msgBox.setStandardButtons(QMessageBox.Ok)
            msgBox.exec_()

    def validate(self):
        result = True
        message = ""
        details = ""

        isAngle = self.radioButtonAngle.isChecked()
        if isAngle:
            angle = self.lineEditArcAngle.text()
            if not isFloat(angle) or float(angle) <= 0:
                result = False
                details = u"The 'Angle' field must contain a number greater than 0.0"
        else:
            numberOfPoints = self.lineEditArcNumberOfPoints.text()
            if not isInt(numberOfPoints) or int(numberOfPoints) <= 0:
                result = False
                details = u"The 'Number of points' field must contain an integer greater than 0"
      
        maxLimitPreview=self.lineEditLimitPreviewGeometries.text()
        if not isInt(maxLimitPreview) or int(maxLimitPreview) <= 0:
            result=False
            details+=u"The limit of the number of geometries to preview must be a positive integer"
    
        if not result:
            message = "There were errors in the form:"
                    
        return result, message, details



def isFloat(s):
    try:
        float(s)
        return True
    except ValueError:
        return False



def isInt(s):
    try:
        int(s)
        return True
    except ValueError:
        return False