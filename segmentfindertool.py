# -*- coding: utf-8 -*-


from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *

import vectorlayerutils
import sys
from snapper import Snapper

# Vertex Finder Tool class
class SegmentFinderTool(QgsMapTool):

    segmentFound = pyqtSignal(object, object)

    def __init__(self, canvas):
        QgsMapTool.__init__(self, canvas)
        self.canvas = canvas
        # our own fancy cursor
        self.cursor = QCursor(QPixmap(["16 16 3 1",
                                      "      c None",
                                      ".     c #FF0000",
                                      "+     c #FFFFFF",
                                      "                ",
                                      "       +.+      ",
                                      "      ++.++     ",
                                      "     +.....+    ",
                                      "    +.     .+   ",
                                      "   +.   .   .+  ",
                                      "  +.    .    .+ ",
                                      " ++.    .    .++",
                                      " ... ...+... ...",
                                      " ++.    .    .++",
                                      "  +.    .    .+ ",
                                      "   +.   .   .+  ",
                                      "   ++.     .+   ",
                                      "    ++.....+    ",
                                      "      ++.++     ",
                                      "       +.+      "]))
        
        self.layers=None
                                    
    def canvasPressEvent(self, event):
        # Get the click
        x = event.pos().x()
        y = event.pos().y()
        
        if self.canvas.currentLayer() <> None or (self.layers <> None and len(self.layers) > 0):
            # the clicked point is our starting point
            startingPoint = QPoint(x, y)
            
            if self.layers == None or len(self.layers) == 0:
                # we snap to the current layer 
                layers=[self.canvas.currentLayer()]
            else:
                # we snap to the layers explicitly defined
                layers=self.layers
                
            snapper=Snapper(self.canvas, layers, QgsSnapper.SnapToSegment)
            snappingResult=snapper.snap(startingPoint)
                             
            if snappingResult:
                # tell the world about the segment
                mapPoint = self.toMapCoordinates(event.pos())
                self.segmentFound.emit(snappingResult, mapPoint)
            else:
                # warn about missing snapping tolerance if appropriate
                self.showSettingsWarning()
    
    def canvasMoveEvent(self, event):
        pass
    
    def canvasReleaseEvent(self, event):
        pass
              
    def showSettingsWarning(self):
        # get the setting for displaySnapWarning
        settings = QSettings()
        settingsLabel = "/UI/displaySnapWarning"
        displaySnapWarning = bool(settings.value(settingsLabel))
        
        # only show the warning if the setting is true
        if displaySnapWarning:    
            m = QgsMessageViewer()
            m.setWindowTitle("Snap tolerance")
            m.setCheckBoxText("Don't show this message again")
            m.setCheckBoxVisible(True)
            m.setCheckBoxQSettingsLabel(settingsLabel)
            m.setMessageAsHtml("<p>Could not snap segment.</p><p>Have you set the tolerance in Settings > Project Properties > General?</p>")
            m.showMessage()
      
    def activate(self):
        self.canvas.setCursor(self.cursor)
    
    def deactivate(self):
        pass
    
    def isZoomTool(self):
        return False
    
    def isTransient(self):
        return False
      
    def isEditTool(self):
        return True
    