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

class MirrorDigitizingMode(QgsMapToolEmitPoint):
    
    def __init__(self, iface, digitizingTools):
        self.iface = iface
        self.digitizingTools = digitizingTools
        QgsMapToolEmitPoint.__init__(self, self.iface.mapCanvas())
        
        self.messageBarUtils = MessageBarUtils(iface)
        
        self.rubberBandMirrorAxis = QgsRubberBand(self.iface.mapCanvas())
        self.rubberBandMirrorAxis.setColor(QColor(255, 0, 0))
        self.rubberBandMirrorAxis.setWidth(2)
        
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
        
        self.rubberBandMirrorAxis.reset(QGis.Line)
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
            self.messageBarUtils.showMessage("Mirror", "Select first point of mirror line", duration=0)
        elif self.step == 1:
            self.messageBarUtils.removeAllMessages()
            self.messageBarUtils.showMessage("Mirror", "Select second point of mirror line",duration=0)
        elif self.step == 2:
            if self.layer.selectedFeatureCount() == 0:
                self.messageBarUtils.showYesCancel("Mirror", "No feature selected in Layer %s. Proceed on full layer?" % self.layer.name(), 
                                                   QgsMessageBar.WARNING, self.doMirror, self.deactivate)
                return
            
            self.doMirror()
   
    def doMirror(self):        
        
            
        _, progress = self.messageBarUtils.showProgress("Mirror", "Running...", QgsMessageBar.INFO)
        
        try:
                
            self.rubberBandGeometriesPreview.reset(QGis.Line)
            
            self.layer.beginEditCommand("Mirror")
            
            ok = self.prepareMirror()
            
            if not ok:
                self.messageBarUtils.showMessage("Mirror", "Invalid mirror line.", QgsMessageBar.WARNING, duration=5)
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
                
                # perform mirror in map coordinates instead of layer coordinates
                inGeom.transform(self.crsTransformReverse)
                
                # break into multiple geometries if needed
                if inGeom.isMultipart():
                    geometries = inGeom.asMultiPolyline()
                    outGeom = []
                    
                    for g in geometries:
                        polyline = self.mirrorPolyline(g)
                        outGeom.append(polyline)
                        
                    outGeom = QgsGeometry.fromMultiPolyline(outGeom)
                else:
                    polyline = self.mirrorPolyline(inGeom.asPolyline())
                    outGeom = QgsGeometry.fromPolyline(polyline)
                    
                outGeom.transform(self.crsTransform)
                
                # beeeeeuh... Cannot make QPyNullVariant work
                # deleteAttribute with string is masked...
                # so...
                outFeat.initAttributes(len(attrs))
                for index in range(len(attrs)):
                    if index <> pgidIndex:
                        outFeat.setAttribute(index, attrs[index]) 
                outFeat.setGeometry(outGeom) 
                ok=self.layer.addFeature(outFeat)
                current += 1
                progress.setValue(int(current * total))
                
            self.messageBarUtils.showMessage("Mirror", "Success", QgsMessageBar.INFO, 5)
            self.layer.endEditCommand()

        except Exception as e:
            QgsMessageLog.logMessage(repr(e))
            self.messageBarUtils.showMessage("Mirror", "There was an error performing this command. See QGIS Message log for details.", QgsMessageBar.CRITICAL, duration=5)
            self.layer.destroyEditCommand()
            
        finally:
            self.iface.mapCanvas().freeze(False)    
            self.iface.mapCanvas().refresh()
            self.iface.mapCanvas().unsetMapTool(self)
        
         
    def prepareMirror(self):
        # rubber bands are in crs of map canvas
        self.layerStartPoint = self.startPoint
        self.layerEndPoint = self.endPoint
        
        dx = self.layerEndPoint.x() - self.layerStartPoint.x()
        dy = self.layerEndPoint.y() - self.layerStartPoint.y()
        norm = sqrt(dx**2 + dy**2)
        if norm == 0:
            return False
        
        self.layerEndPoint = QgsPoint( self.layerStartPoint.x() + dx / norm, self.layerStartPoint.x() + dy / norm)
        # consider the origin at startPoint
        self.normedAxis = QgsPoint(dx / norm, dy / norm)
        return True
         
    def mirrorPolyline(self, polyline):
        for vertex in polyline:
            # project
            relSP = QgsPoint(vertex.x() - self.layerStartPoint.x(), vertex.y() - self.layerStartPoint.y())
            dp = relSP.x() * self.normedAxis.x() + relSP.y() * self.normedAxis.y()
            vertex.setX(self.layerStartPoint.x() - relSP.x() + 2 * dp * self.normedAxis.x())
            vertex.setY(self.layerStartPoint.y() - relSP.y() + 2 * dp * self.normedAxis.y())
            
        return polyline
    
    
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
        
            self.rubberBandMirrorAxis.reset(QGis.Line)
            self.rubberBandMirrorAxis.addPoint(self.startPoint)
            self.rubberBandMirrorAxis.addPoint(self.endPoint)
            self.rubberBandMirrorAxis.show()            
            
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
            self.rubberBandMirrorAxis.reset(QGis.Line)
            self.rubberBandMirrorAxis.addPoint(self.startPoint)
            self.rubberBandMirrorAxis.addPoint(self.endPoint)
            self.rubberBandMirrorAxis.show()
            
            self.updateGeometriesPreview()
            
    def updateGeometriesPreview(self):
        ok = self.prepareMirror()
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
            
            # break into multiple geometries if needed
            if inGeom.isMultipart():
                geometries = inGeom.asMultiPolyline()
                
                for g in geometries:
                    polyline = self.mirrorPolyline(g)
                    # polyline in map coordinates
                    self.rubberBandGeometriesPreview.addGeometry(QgsGeometry.fromPolyline(polyline), None)
                    
            else:
                polyline = self.mirrorPolyline(inGeom.asPolyline())
                self.rubberBandGeometriesPreview.addGeometry(QgsGeometry.fromPolyline(polyline), None)
                
            
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