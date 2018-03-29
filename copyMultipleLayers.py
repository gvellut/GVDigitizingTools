# -*- coding: utf-8 -*-

# Import the PyQt and QGIS libraries
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *
from messagebarutils import MessageBarUtils
import vectorlayerutils
import constants

class CopyMultipleLayersDigitizingMode(QgsMapToolEmitPoint):
    
    MESSAGE_HEADER = "Copy from multiple layers"
    
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
        
        self.rubberBandPointsPreview = QgsRubberBand(self.iface.mapCanvas())
        self.rubberBandPointsPreview.setColor(QColor(0, 255, 0))
        self.rubberBandPointsPreview.setWidth(2)
        self.rubberBandPointsPreview.setIcon(QgsRubberBand.ICON_CIRCLE)
        
        self.rubberBandSnap = QgsRubberBand(self.iface.mapCanvas())
        self.rubberBandSnap.setColor(QColor(255, 51, 153))
        self.rubberBandSnap.setIcon(QgsRubberBand.ICON_CROSS)
        self.rubberBandSnap.setIconSize(12)
        self.rubberBandSnap.setWidth(3)
        
        self.isEmittingPoint = False
        
        # we need a snapper, so we use the MapCanvas snapper  
        self.snapper = QgsMapCanvasSnapper(self.iface.mapCanvas())

        self.reset()
    
    def setLayer(self, layer):
        # this mode ignores the currently selected layer
        pass
        
    def reset(self, clearMessages = True):
        self.step = 0
        
        self.rubberBandMoveAxis.reset(QGis.Line)
        self.rubberBandGeometriesPreview.reset(QGis.Line)
        self.rubberBandPointsPreview.reset(QGis.Point)
        self.rubberBandSnap.reset(QGis.Point)
        
        settings=QSettings()
        self.isPreviewEnabled=settings.value(constants.PREVIEW_ENABLED,type=bool)
        self.isLimitPreviewEnabled=settings.value(constants.PREVIEW_LIMIT_ENABLED,type=bool)
        self.maxLimitPreview=settings.value(constants.PREVIEW_LIMIT_MAX,type=int)
        
        self.isEmittingPoint=False
        
        if clearMessages:
            self.messageBarUtils.removeAllMessages()
        
    def deactivate(self):
        self.reset()
        super(QgsMapToolEmitPoint, self).deactivate()
        
    def next(self):
        if self.step == 0:
            self.messageBarUtils.showMessage(self.MESSAGE_HEADER, "Select base point of displacement", duration=0)
        elif self.step == 1:
            self.messageBarUtils.removeAllMessages()
            self.messageBarUtils.showButton(self.MESSAGE_HEADER, "Select second point of displacement","Done",buttonCallback=self.done)
        elif self.step == 2:
            totalLayers = 0
            layersWithNoSelection = 0
            
            layers = self.iface.legendInterface().selectedLayers()
            for layer in layers:
                if layer.type() == QgsMapLayer.VectorLayer:
                    totalLayers += 1
                    if layer.selectedFeatureCount() == 0:
                        layersWithNoSelection += 1
            
            if totalLayers == layersWithNoSelection:      
                self.messageBarUtils.showMessage(self.MESSAGE_HEADER, "None of the layers selected in the TOC has a selection. Nothing done", 
                                                   QgsMessageBar.WARNING)
                self.iface.mapCanvas().refresh()
                self.iface.mapCanvas().unsetMapTool(self)
                return
            elif layersWithNoSelection != 0 :
                self.messageBarUtils.showYesCancel(self.MESSAGE_HEADER, "%d out of %d vector layers have no selection. Proceed on the other layers?" % (layersWithNoSelection, totalLayers), 
                                                   QgsMessageBar.WARNING, self.doMove, self.deactivate)
                return
            
            
            self.doCopy()
   
    def doCopy(self):        
        _, progress = self.messageBarUtils.showProgress(self.MESSAGE_HEADER, "Running...", QgsMessageBar.INFO)
                
        self.rubberBandGeometriesPreview.reset(QGis.Line)
        self.rubberBandPointsPreview.reset(QGis.Point)
        
        currentLayer = None
        isEditable = []
        
        try:
            ok = self.prepareDisplacement()
            if not ok:
                self.messageBarUtils.showMessage(self.MESSAGE_HEADER, "Invalid displacement.", QgsMessageBar.WARNING, duration=5)
                return
            
            self.iface.mapCanvas().freeze(True)
    
            inGeom = QgsGeometry()
            outFeat = QgsFeature()
    
            current = 0
            
            layers = self.iface.legendInterface().selectedLayers()
            for layer in layers:
                # only deal with selected features of the selected layers
                if layer.type() == QgsMapLayer.VectorLayer and layer.selectedFeatureCount() > 0:
                    currentLayer = layer
                    if layer.isEditable():
                        isEditable.append(True)
                        layer.beginEditCommand("Copy from multiple layers")
                    else:
                        isEditable.append(False)
                        layer.startEditing() 
                
                    crsDest = layer.crs()
                    canvas = self.iface.mapCanvas()
                    mapRenderer = canvas.mapSettings()
                    crsSrc = mapRenderer.destinationCrs()
                    crsTransform = QgsCoordinateTransform(crsSrc, crsDest)
                    # cannot indicate direction in QgsGeometry.transform
                    crsTransformReverse = QgsCoordinateTransform(crsDest, crsSrc)
                    
                    features = vectorlayerutils.features(layer)
                    total = 100.0 / float(len(features))
                    pgidIndex=layer.fieldNameIndex("gid")
                    progress.setValue(0)
                    for f in features:
                        inGeom = f.geometry()
                        attrs = f.attributes()
                        
                        # perform displacement in map coordinates instead of layer coordinates
                        inGeom.transform(crsTransformReverse)
                        outGeom = self.moveGeometry(inGeom)
                        outGeom.transform(crsTransform)
                        
                        outFeat.initAttributes(len(attrs))
                        for index in range(len(attrs)):
                            if index <> pgidIndex:
                                outFeat.setAttribute(index, attrs[index]) 
                        outFeat.setGeometry(outGeom) 
                        layer.addFeature(outFeat)
                            
                        current += 1
                        progress.setValue(int(current * total))
                    
            currentLayer = None
            self.messageBarUtils.showMessage(self.MESSAGE_HEADER, "Success", QgsMessageBar.INFO, 5)
            # commit modifications in all layers at the end
            count = 0
            layers = self.iface.legendInterface().selectedLayers()
            for layer in layers:
                # only deal with selected features of the selected layers
                if layer.type() == QgsMapLayer.VectorLayer and layer.selectedFeatureCount() > 0:
                    if isEditable[count]:
                        layer.endEditCommand()
                    else:
                        layer.commitChanges()
                    
                    count += 1

        except Exception as e:
            raise
            QgsMessageLog.logMessage(repr(e))
            self.messageBarUtils.showMessage(self.MESSAGE_HEADER, 
                                             "There was an error performing this command. See QGIS Message log for details.", 
                                             QgsMessageBar.CRITICAL, duration=5)
            
            # rollback modifications in all layers
            count = 0
            layers = self.iface.legendInterface().selectedLayers()
            for layer in layers:
                # only deal with selected features of the selected layers
                if layer.type() == QgsMapLayer.VectorLayer and layer.selectedFeatureCount() > 0:
                    if isEditable[count]:
                        layer.destroyEditCommand()
                    else:
                        layer.rollBack()
                    # subsequent layers have not been modified   
                    if layer == currentLayer:
                        break
                    
                    count += 1
            
            
        finally:
            self.iface.mapCanvas().freeze(False)    
            self.iface.mapCanvas().refresh()
            
        
        self.resetCopyMultipleLayers()
        self.next()
        
    
    def resetCopyMultipleLayers(self):
        self.step=1
        
    def done(self):
        self.reset()
        self.iface.mapCanvas().unsetMapTool(self)
         
    def prepareDisplacement(self):
        # rubber bands are in crs of map canvas
        self.dx = self.endPoint.x() - self.startPoint.x()
        self.dy = self.endPoint.y() - self.startPoint.y()
        return True
    
    def moveGeometry(self, geom):
        geom.translate(self.dx,self.dy)
        return geom
                
    def moveVertex(self, vertex):
        vertex.setX(vertex.x() + self.dx)
        vertex.setY(vertex.y() + self.dy)
        return vertex
    
    def enter(self):
        #ignore
        pass
    
    def canvasPressEvent(self, e):
        pass
        

    def canvasReleaseEvent(self, e):
        if e.button() == Qt.RightButton:
            if self.step == 1:
                self.done()
        
        if self.step == 0:
            
            # we snap to the current layer (we don't have exclude points and use the tolerances from the qgis properties)
            pos = QPoint(e.pos().x(), e.pos().y())
            result = self.snap(pos)
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
            result = self.snap(pos)
            if result != []:
                self.endPoint = QgsPoint(result[0].snappedVertex)
            else:
                self.endPoint = self.toMapCoordinates(e.pos())
            
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
        self.rubberBandPointsPreview.reset(QGis.Point)
        
        if not ok:
            return
        
        if not self.isPreviewEnabled:
            return
        
        layers = self.iface.legendInterface().selectedLayers()
        for layer in layers:
            if layer.type() == QgsMapLayer.VectorLayer and layer.selectedFeatureCount() > 0:
                crsDest = layer.crs()
                canvas = self.iface.mapCanvas()
                mapRenderer = canvas.mapSettings()
                crsSrc = mapRenderer.destinationCrs()
                crsTransformReverse = QgsCoordinateTransform(crsDest, crsSrc)
                
                if self.isLimitPreviewEnabled:
                    maxCount=self.maxLimitPreview
                else:
                    maxCount=layer.featureCount()
                    
                currentCount=0
                features = vectorlayerutils.features(layer)
                for f in features:
                    inGeom = f.geometry()
                    inGeom.transform(crsTransformReverse)
                    inGeom = self.moveGeometry(inGeom)
                    # in map coordinates
                    if inGeom.type() == QGis.Point:
                        self.rubberBandPointsPreview.addGeometry(inGeom, None)
                    else:
                        self.rubberBandGeometriesPreview.addGeometry(inGeom, None)
                    
                    currentCount+=1
                    if currentCount >= maxCount:
                        break
                    
        self.rubberBandPointsPreview.show()
        self.rubberBandGeometriesPreview.show()
        
    def snap(self, pos):
        if self.digitizingTools.isBackgroundSnapping:
            (_, result) = self.snapper.snapToBackgroundLayers(pos)
        else:
            (_, result) = self.snapper.snapToCurrentLayer(pos, QgsSnapper.SnapToVertex)
        return result
    