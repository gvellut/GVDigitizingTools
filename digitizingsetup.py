# -*- coding: utf-8 -*-

# Import the PyQt and QGIS libraries
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *

import math


class DigitizingSetup(QObject):
    
    FORM_POPUP_SETTING = "Qgis/digitizing/disable_enter_attribute_values_dialog"
    
    escapePressed = pyqtSignal(object)
    returnPressed = pyqtSignal(object)

    def __init__(self, iface):
        QObject.__init__(self)
        self.iface = iface
        self.mapCanvas = iface.mapCanvas()
        
        s = QSettings()
        self.previousFormPopup = s.value(DigitizingSetup.FORM_POPUP_SETTING, False)
        self.previousTopologicalEditing, _ = QgsProject.instance().readBoolEntry("Digitizing", 
                    "TopologicalEditing")
        
        self.enableEventFilter = False

    def activate(self):
        qDebug("Digit Setup active")
  
        # update some settings
        s = QSettings()
        self.previousFormPopup = s.value(DigitizingSetup.FORM_POPUP_SETTING, False)
        s.setValue("Qgis/digitizing/disable_enter_attribute_values_dialog", True)
        
        self.previousTopologicalEditing, _ = QgsProject.instance().readBoolEntry("Digitizing", 
                    "TopologicalEditing")
        QgsProject.instance().writeEntry("Digitizing", 
                    "TopologicalEditing", True)
        
        self.enableEventFilter = True
              

    def deactivate(self):
        qDebug("Digit Setup inactive")
            
        s = QSettings()
        s.setValue(DigitizingSetup.FORM_POPUP_SETTING, self.previousFormPopup)
        QgsProject.instance().writeEntry("Digitizing", 
                    "TopologicalEditing", self.previousTopologicalEditing)
        
        self.enableEventFilter = False
        