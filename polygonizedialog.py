# -*- coding: utf-8 -*-

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
# Initialize Qt resources from file resources.py
import resources_rc
from polygonizedialog_ui import Ui_PolygonizeDialog

import constants

class PolygonizeDialog(QDialog, Ui_PolygonizeDialog):
    def __init__(self, polygonLayers, nonDigitLayerIndex):
        QDialog.__init__(self)
        self.setupUi(self)
        
        self.polygonLayers = polygonLayers
        for polygonLayer in polygonLayers:
            self.comboBoxLayers.addItem(polygonLayer.name(), polygonLayer)
        if nonDigitLayerIndex <> None:
            self.comboBoxLayers.setCurrentIndex(nonDigitLayerIndex)
        self.checkBoxAppend.setChecked(True)

    def accept(self):
        self.append = self.checkBoxAppend.isChecked()
        self.selectedLayer = self.polygonLayers[self.comboBoxLayers.currentIndex()]
        self.done(QDialog.Accepted)
       
