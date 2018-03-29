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

class CopyDigitizingMode(QgsMapToolEmitPoint):
    
    MESSAGE_HEADER = "Copy"
    
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
        self.rubberBandSnap.setWidth (3)
        
        self.isEmittingPoint = False
        
        # we need a snapper, so we use the MapCanvas snapper  
        self.snapper = QgsMapCanvasSnapper(self.iface.mapCanvas())

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
            self.messageBarUtils.showMessage(CopyDigitizingMode.MESSAGE_HEADER, "Select base point of displacement", duration=0)
        elif self.step == 1:
            self.messageBarUtils.showButton(CopyDigitizingMode.MESSAGE_HEADER, "Select second point of displacement","Done",buttonCallback=self.done)
        elif self.step == 2:
            if self.layer.selectedFeatureCount() == 0:
                self.messageBarUtils.showYesCancel(CopyDigitizingMode.MESSAGE_HEADER, "No feature selected in Layer %s. Proceed on full layer?" % self.layer.name(), 
                                                   QgsMessageBar.WARNING, self.doCopy, self.deactivate)
                return
            
            self.doCopy()
   
    def doCopy(self): 
        _, progress = self.messageBarUtils.showProgress(CopyDigitizingMode.MESSAGE_HEADER, "Running...", QgsMessageBar.INFO)
        
        try:
                
            self.rubberBandGeometriesPreview.reset(QGis.Line)
            
            self.layer.beginEditCommand(CopyDigitizingMode.MESSAGE_HEADER)
            
            ok = self.prepareDisplacement()
            
            if not ok:
                self.messageBarUtils.showMessage(CopyDigitizingMode.MESSAGE_HEADER, "Invalid displacement.", QgsMessageBar.WARNING, duration=5)
                self.layer.destroyEditCommand()
                return
            
            self.iface.mapCanvas().freeze(True)
    
            outFeat = QgsFeature()
    
            current = 0
            features = vectorlayerutils.features(self.layer)
            total = 100.0 / float(len(features))
            pgidIndex=self.layer.fieldNameIndex("gid")
            for f in features:
                inGeom = f.geometry()
                attrs = f.attributes()
                
                # perform displacement in map coordinates instead of layer coordinates
                inGeom.transform(self.crsTransformReverse)
                outGeom=self.movePolyline(inGeom)
                outGeom.transform(self.crsTransform)
                
                outFeat.initAttributes(len(attrs))
                for index in range(len(attrs)):
                    if index <> pgidIndex:
                        outFeat.setAttribute(index, attrs[index]) 
                outFeat.setGeometry(outGeom) 
                self.layer.addFeature(outFeat)
                    
                current += 1
                progress.setValue(int(current * total))
                
            self.messageBarUtils.showMessage(CopyDigitizingMode.MESSAGE_HEADER, "Success", QgsMessageBar.INFO, 5)
            self.layer.endEditCommand()

        except Exception as e:
            QgsMessageLog.logMessage(repr(e))
            self.messageBarUtils.showMessage(CopyDigitizingMode.MESSAGE_HEADER, 
                                             "There was an error performing this command. See QGIS Message log for details.", 
                                             QgsMessageBar.CRITICAL, duration=5)
            self.layer.destroyEditCommand()
            
        finally:
            self.iface.mapCanvas().freeze(False)    
            self.iface.mapCanvas().refresh()
            
        self.resetCopy()
        self.next()
        
    def resetCopy(self):
        self.step=1
        
    
    def done(self):
        self.reset()
        self.iface.mapCanvas().unsetMapTool(self)
         
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
        # use right button instead of clicking on button in message bar
        if e.button() == Qt.RightButton:
            if self.step == 1:
                self.done()
        elif e.button() == Qt.LeftButton:    
            if self.step == 0:
                modifiers = e.modifiers()
                if modifiers == Qt.ControlModifier:
                    self.isDuplicate = True
                    
                # we snap to the current layer (we don't have exclude points and use the tolerances from the qgis properties)
                pos = QPoint(e.pos().x(), e.pos().y())
                result=self.snap(pos)
                if result != []:
                    self.startPoint = QgsPoint(result[0].snappedVertex)
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
                result=self.snap(pos)
                if result != []:
                    self.endPoint = QgsPoint(result[0].snappedVertex)
                else:
                    self.endPoint = self.toMapCoordinates(e.pos())
                
                self.step = 2
                self.next()
        

    def canvasReleaseEvent(self, e):
        pass

    def canvasMoveEvent(self, e):
        pos = QPoint(e.pos().x(), e.pos().y())
        result=self.snap(pos)
        self.rubberBandSnap.reset(QGis.Point)
        if result != []:
            self.rubberBandSnap.addPoint(result[0].snappedVertex, True)
        
        if not self.isEmittingPoint:
            return
            
        if self.step == 1:
            if result != []:
                self.endPoint = QgsPoint(result[0].snappedVertex)
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