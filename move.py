# -*- coding: utf-8 -*-

# Import the PyQt and QGIS libraries
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *
from math import sqrt
from messagebarutils import MessageBarUtils
import vectorlayerutils
import constants
from functools import partial

class MoveDigitizingMode(QgsMapToolEmitPoint):
    
    MESSAGE_HEADER = "Move"
    
    def __init__(self, iface, digitizingTools):
        self.iface = iface
        self.digitizingTools = digitizingTools
        QgsMapToolEmitPoint.__init__(self, self.iface.mapCanvas())
        
        self.messageBarUtils = MessageBarUtils(iface)
        
        self.rubberBandMoveAxis = QgsRubberBand(self.iface.mapCanvas())
        self.rubberBandMoveAxis.setColor(QColor(255, 0, 0))
        self.rubberBandMoveAxis.setWidth(2)
        
        self.rubberBandGeometriesPreview = QgsRubberBand(self.iface.mapCanvas())
        self.rubberBandGeometriesPreview.setColor(QColor(0, 255, 0))
        self.rubberBandGeometriesPreview.setWidth(1)
        
        self.rubberBandSnap = QgsRubberBand(self.iface.mapCanvas())
        self.rubberBandSnap.setColor(QColor(255, 51, 153))
        self.rubberBandSnap.setIcon(QgsRubberBand.ICON_CROSS)
        self.rubberBandSnap.setIconSize(12)
        self.rubberBandSnap.setWidth(3)
        
        self.isEmittingPoint = False
        
        # we need a snapper, so we use the MapCanvas snapper  
        self.snapper = QgsMapCanvasSnapper(self.iface.mapCanvas())
        
        self.dx=None
        self.dy=None

        self.layer = None
        self.reset()
    
    def setLayer(self, layer):
        self.layer = layer
        
        crsDest = self.layer.crs()
        canvas = self.iface.mapCanvas()
        mapRenderer = canvas.mapSettings()
        crsSrc = mapRenderer.destinationCrs()
        self.crsTransform = QgsCoordinateTransform(crsSrc, crsDest)
        # cannot indicate direction in QgsGeometry.transform
        self.crsTransformReverse = QgsCoordinateTransform(crsDest, crsSrc)
        
        
    def reset(self, clearMessages = True):
        self.step = 0
        
        self.rubberBandMoveAxis.reset(QGis.Line)
        self.rubberBandGeometriesPreview.reset(QGis.Line)
        self.rubberBandSnap.reset(QGis.Point)
        
        settings=QSettings()
        self.isPreviewEnabled=settings.value(constants.PREVIEW_ENABLED,type=bool)
        self.isLimitPreviewEnabled=settings.value(constants.PREVIEW_LIMIT_ENABLED,type=bool)
        self.maxLimitPreview=settings.value(constants.PREVIEW_LIMIT_MAX,type=int)
        
        if clearMessages:
            self.messageBarUtils.removeAllMessages()
        
    def deactivate(self):
        self.reset()
        super(QgsMapToolEmitPoint, self).deactivate()
        
    def next(self):
        if self.step == 0:
            if self.dx <> None and self.dy <> None:
                self.messageBarUtils.showButton(self.MESSAGE_HEADER, "Select base point of displacement", "Apply previous displacement", buttonCallback=self.applyPrevious)
            else:
                self.messageBarUtils.showMessage(self.MESSAGE_HEADER, "Select base point of displacement", duration=0)
        elif self.step == 1:
            self.messageBarUtils.removeAllMessages()
            self.messageBarUtils.showMessage(self.MESSAGE_HEADER, "Select second point of displacement",duration=0)
        elif self.step == 2:
            if self.layer.selectedFeatureCount() == 0:
                self.messageBarUtils.showYesCancel(self.MESSAGE_HEADER, "No feature selected in Layer %s. Proceed on full layer?" % self.layer.name(), 
                                                   QgsMessageBar.WARNING, self.doMove, 
                                                   lambda: self.iface.mapCanvas().unsetMapTool(self))
                return
            
            self.doMove()
   
    def doMove(self, usePrevious=False):   
        _, progress = self.messageBarUtils.showProgress(self.MESSAGE_HEADER, "Running...", QgsMessageBar.INFO)
        
        try:
                
            self.rubberBandGeometriesPreview.reset(QGis.Line)
            
            self.layer.beginEditCommand(self.MESSAGE_HEADER)
            
            if not usePrevious:
                ok = self.prepareDisplacement()
                if not ok:
                    self.messageBarUtils.showMessage(self.MESSAGE_HEADER, "Invalid displacement.", QgsMessageBar.WARNING, duration=5)
                    self.layer.destroyEditCommand()
                    return
            
            self.iface.mapCanvas().freeze(True)
    
            inGeom = QgsGeometry()
    
            current = 0
            features = vectorlayerutils.features(self.layer)
            total = 100.0 / float(len(features))
            for f in features:
                inGeom = f.geometry()
                
                # perform displacement in map coordinates instead of layer coordinates
                inGeom.transform(self.crsTransformReverse)
                outGeom=self.movePolyline(inGeom)
                outGeom.transform(self.crsTransform)
                
                self.layer.changeGeometry(f.id(), outGeom)
                    
                current += 1
                progress.setValue(int(current * total))
                
            self.messageBarUtils.showMessage(self.MESSAGE_HEADER, "Success", QgsMessageBar.INFO, 5)
            self.layer.endEditCommand()

        except Exception as e:
            QgsMessageLog.logMessage(repr(e))
            self.messageBarUtils.showMessage(MoveDigitizingMode.MESSAGE_HEADER, 
                                             "There was an error performing this command. See QGIS Message log for details.", 
                                             QgsMessageBar.CRITICAL, duration=5)
            self.layer.destroyEditCommand()
            
        finally:
            self.iface.mapCanvas().freeze(False)    
            self.iface.mapCanvas().refresh()
            self.iface.mapCanvas().unsetMapTool(self)
        
         
    def applyPrevious(self):
        if len(self.selectedFeatureCount()) == 0:
            self.messageBarUtils.showYesCancel(MoveDigitizingMode.MESSAGE_HEADER, "No feature selected in Layer %s. Proceed on full layer?" % self.layer.name(), 
                                               QgsMessageBar.WARNING, partial(self.doMove, True), 
                                               lambda: self.iface.mapCanvas().unsetMapTool(self))
            return
        
        self.doMove(True)
         
    def prepareDisplacement(self):
        # rubber bands are in crs of map canvas
        self.dx = self.endPoint.x() - self.startPoint.x()
        self.dy = self.endPoint.y() - self.startPoint.y()
        return True
         
    def movePolyline(self, geom):
        geom.translate(self.dx, self.dy)
        return geom
    
    def enter(self):
        #ignore
        pass
    
    def canvasPressEvent(self, e):
        pass
        

    def canvasReleaseEvent(self, e):
        if self.step == 0:
            
            # we snap to the current layer (we don't have exclude points and use the tolerances from the qgis properties)
            pos = QPoint(e.pos().x(), e.pos().y())
            result = self.snap(pos)
                
            if result != []:
                self.startPoint = result[0].snappedVertex
            else:
                self.startPoint = self.toMapCoordinates(e.pos())
                
            self.endPoint = self.startPoint
            self.isEmittingPoint = True
        
            self.rubberBandMoveAxis.reset(QGis.Line)
            self.rubberBandMoveAxis.addPoint(self.startPoint)
            self.rubberBandMoveAxis.addPoint(self.endPoint)
            self.rubberBandMoveAxis.show()            
            
            self.step = 1
            self.next()
        elif self.step == 1:
            pos = QPoint(e.pos().x(), e.pos().y())
            result = self.snap(pos)
            if result != []:
                self.endPoint = result[0].snappedVertex
            else:
                self.endPoint = self.toMapCoordinates(e.pos())
                
            self.isEmittingPoint = False
            
            self.step = 2
            self.next()

    def canvasMoveEvent(self, e):
        pos = QPoint(e.pos().x(), e.pos().y())
        result = self.snap(pos)
        self.rubberBandSnap.reset(QGis.Point)
        if result != []:
            self.rubberBandSnap.addPoint(result[0].snappedVertex, True)
        
        if not self.isEmittingPoint:
            return
            
        if self.step == 1:
            if result != []:
                self.endPoint = result[0].snappedVertex
            else:
                self.endPoint = self.toMapCoordinates(e.pos())
            self.rubberBandMoveAxis.reset(QGis.Line)
            self.rubberBandMoveAxis.addPoint(self.startPoint)
            self.rubberBandMoveAxis.addPoint(self.endPoint)
            self.rubberBandMoveAxis.show()
            
            self.updateGeometriesPreview()
            
    def updateGeometriesPreview(self):
        ok = self.prepareDisplacement()
        self.rubberBandGeometriesPreview.reset(QGis.Line)
        
        if not ok:
            return
        
        if not self.isPreviewEnabled:
            return
        
        if self.isLimitPreviewEnabled:
            maxCount=self.maxLimitPreview
        else:
            maxCount=self.layer.featureCount()
        
        currentCount=0
        features = vectorlayerutils.features(self.layer)
        for f in features:
            inGeom = f.geometry()
            inGeom.transform(self.crsTransformReverse)
            inGeom=self.movePolyline(inGeom)
            self.rubberBandGeometriesPreview.addGeometry(inGeom, None)
            
            currentCount+=1
            if currentCount >= maxCount:
                break
                
        self.rubberBandGeometriesPreview.show()
        
    def snap(self, pos):
        if self.digitizingTools.isBackgroundSnapping:
            (_, result) = self.snapper.snapToBackgroundLayers(pos)
        else:
            (_, result) = self.snapper.snapToCurrentLayer(pos, QgsSnapper.SnapToVertex)
        return result
    