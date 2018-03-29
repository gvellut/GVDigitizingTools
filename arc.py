# -*- coding: utf-8 -*-

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *
from messagebarutils import MessageBarUtils
from segmentfindertool import SegmentFinderTool
from arcutils import CircularArc

import constants

class DrawArcDigitizingMode(QgsMapToolEmitPoint):
    
    MESSAGE_HEADER = "Draw Arc"
    
    def __init__(self, iface):
        self.iface = iface
        QgsMapToolEmitPoint.__init__(self, self.iface.mapCanvas())
        
        self.messageBarUtils = MessageBarUtils(iface)
        
        self.segmentFinderTool = SegmentFinderTool(self.iface.mapCanvas())
        
        self.rubberBandBase = QgsRubberBand(self.iface.mapCanvas())
        self.rubberBandBase.setColor(QColor(255, 0, 0))
        self.rubberBandBase.setWidth(2)

        self.layer = None
        self.reset()
    
    def setLayer(self, layer):
        self.layer = layer
        
    def reset(self, clearMessages = True):
        self.step = 0
        self.baseEdge = None
        
        self.rubberBandBase.reset(QGis.Line)
        
        try:self.segmentFinderTool.segmentFound.disconnect()
        except Exception: pass
        
        if clearMessages:
            self.messageBarUtils.removeAllMessages()
        
    def deactivate(self):
        self.reset()
        super(QgsMapToolEmitPoint, self).deactivate()
        
    def next(self):
        if self.step == 0:
            self.messageBarUtils.showMessage(DrawArcDigitizingMode.MESSAGE_HEADER, "Select base edge", duration=0)
            self.currentMapTool = self.segmentFinderTool
            self.segmentFinderTool.segmentFound.connect(self.baseEdgeFound)
        elif self.step == 1:
            self.messageBarUtils.showMessage(DrawArcDigitizingMode.MESSAGE_HEADER, "Draw node for arc",duration=0)
            self.currentMapTool = None
        elif self.step == 2:
            self.doDrawArc()
         
    def baseEdgeFound(self, result, pointClicked):
        self.baseEdge = result
        self.segmentFinderTool.segmentFound.disconnect(self.baseEdgeFound)
        self.segmentFinderTool.deactivate()
        
        self.rubberBandBase.reset(QGis.Line)
        self.rubberBandBase.addPoint(result.beforeVertex)
        self.rubberBandBase.addPoint(result.afterVertex, True)
        self.rubberBandBase.show()
        
        self.step = 1
        self.next()
   
    def doDrawArc(self):
        self.messageBarUtils.showMessage(DrawArcDigitizingMode.MESSAGE_HEADER, "Running...", duration=0)
        try:
            # get the actual vertices from the geometry instead of the snapping
            # result vertices which are in map canvas CRS
            featureBase = self._getFeature(self.baseEdge)
            geometryBase = featureBase.geometry()
            
            settings = QSettings()
            method = settings.value(constants.ARC_METHOD,  "")
            if method == constants.ARC_METHOD_NUMBEROFPOINTS:
                value = settings.value(constants.ARC_NUMBEROFPOINTS, 0, type=int)
            else:
                value = settings.value(constants.ARC_ANGLE, 0, type=float)

            # arc done in map canvas coordinate
            g = CircularArc.getInterpolatedArc(self.baseEdge.beforeVertex,  self.arcNode,  self.baseEdge.afterVertex,  method,  value)
            arcVertices = g.asPolyline()
            if len(arcVertices) > 2:
                # to project the vertices of the arc in layer crs
                crsDest = self.layer.crs()
                canvas = self.iface.mapCanvas()
                mapRenderer = canvas.mapSettings()
                crsSrc = mapRenderer.destinationCrs()
                crsTransform = QgsCoordinateTransform(crsSrc, crsDest)
                
                # pass over first and last vertex (bvBase and avBase)
                for i in range(len(arcVertices) - 2, 0, -1):
                    arcVertex = arcVertices[i]
                    arcVertex = crsTransform.transform(arcVertex)
                    geometryBase.insertVertex(arcVertex.x(), arcVertex.y(), self.baseEdge.afterVertexNr)
                    # the newly inserted vertex has the index of the original avBase so all good
                
                self.layer.beginEditCommand(DrawArcDigitizingMode.MESSAGE_HEADER)
                self.layer.changeGeometry(featureBase.id(), geometryBase)
                self.layer.endEditCommand()
                
                self.messageBarUtils.showMessage(DrawArcDigitizingMode.MESSAGE_HEADER, "Success", 
                                                     QgsMessageBar.INFO, duration=5)
            else:
                self.messageBarUtils.showMessage(DrawArcDigitizingMode.MESSAGE_HEADER, "No arc was created", QgsMessageBar.WARNING, duration=5)
                
        except Exception as e:
            self.reset()
            QgsMessageLog.logMessage(repr(e))
            self.messageBarUtils.showMessage(DrawArcDigitizingMode.MESSAGE_HEADER, 
                                             "There was an error performing this command. See QGIS Message log for details", QgsMessageBar.CRITICAL, duration=5)
            
        finally:
            self.iface.mapCanvas().refresh()
            
        self.iface.mapCanvas().unsetMapTool(self)
        
    def _getFeature(self, snappingResult):
        fid = snappingResult.snappedAtGeometry
        feature = QgsFeature()
        fiter = self.layer.getFeatures(QgsFeatureRequest(fid))
        if fiter.nextFeature(feature):
            return feature
        return None
         
    def enter(self):
        #ignore
        pass
    
    def canvasPressEvent(self, e):
        if self.currentMapTool:
            self.currentMapTool.canvasPressEvent(e)
        elif self.step == 1:
            # just point selection
            self.arcNode = self.toMapCoordinates(e.pos())
            self.step = 2
            self.next()

    def canvasReleaseEvent(self, e):
        if self.currentMapTool:
            self.currentMapTool.canvasReleaseEvent(e) 

    def canvasMoveEvent(self, e):
        if self.currentMapTool:
            self.currentMapTool.canvasMoveEvent(e)
 