# -*- coding: utf-8 -*-
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *
from messagebarutils import MessageBarUtils
from segmentfindertool import SegmentFinderTool
import vectorlayerutils  
import constants
from operator import itemgetter
from functools import partial
  
class CenterlineDigitizingMode(QgsMapToolEmitPoint):
    def __init__(self, iface):
        self.iface = iface
        QgsMapToolEmitPoint.__init__(self, self.iface.mapCanvas())
        
        self.messageBarUtils = MessageBarUtils(iface)
        
        self.segmentFinderTool = SegmentFinderTool(self.iface.mapCanvas())
        self.rubberBandSelectedSegment = QgsRubberBand(self.iface.mapCanvas())
        self.rubberBandSelectedSegment.setColor(QColor(255, 0, 0))
        self.rubberBandSelectedSegment.setWidth(2)
        
        self.defaultIndex=None
        self.layer = None
        self.reset()
    
    def setLayer(self, layer):
        self.layer = layer
        
    def reset(self, clearMessages = True):
        self.step = 0
        self.snappingResultFirstEdge = None
        self.snappingResultSecondEdge = None
        self.defaultIndex=None
        
        self.rubberBandSelectedSegment.reset(QGis.Line)
        
        try:self.segmentFinderTool.segmentFound.disconnect()
        except Exception: pass
        
        if clearMessages:
            self.messageBarUtils.removeAllMessages()
            
    def resetCenterline(self):
        self.step = 0
        self.snappingResultFirstEdge = None
        self.snappingResultSecondEdge = None
        self.rubberBandSelectedSegment.reset(QGis.Line)
        self.segmentFinderTool.layers=None
        
    def deactivate(self):
        self.reset()
        QgsMapToolEmitPoint.deactivate(self)
        
    def next(self):
        if self.step == 0:
            self.messageBarUtils.showButton("Centerline", "Select first edge", "Done", buttonCallback=self.done)
            _,candidateLayers,_=self.listCandidateLayers(onlyEditable=False)
            self.segmentFinderTool.layers=candidateLayers
            self.currentMapTool = self.segmentFinderTool
            self.segmentFinderTool.segmentFound.connect(self.firstEdgeFound)
        elif self.step == 1:
            candidates, candidateLayers, defaultIndex=self.listCandidateLayers()
            if self.defaultIndex <> None and defaultIndex < len(candidateLayers):
                defaultIndex=self.defaultIndex
            _,combobox=self.messageBarUtils.showCombobox("Centerline", "Select second edge", candidates, defaultIndex)
            self.currentMapTool = self.segmentFinderTool
            self.segmentFinderTool.segmentFound.connect(partial(self.secondEdgeFound, candidateLayers, combobox))
        elif self.step == 2:
            self.doCenterline()
         
    def firstEdgeFound(self, result, pointClicked):
        self.snappingResultFirstEdge = result
        
        try:self.segmentFinderTool.segmentFound.disconnect() 
        except Exception: pass
        
        self.segmentFinderTool.deactivate()
        
        self.rubberBandSelectedSegment.reset(QGis.Line)
        self.rubberBandSelectedSegment.addPoint(result.beforeVertex)
        self.rubberBandSelectedSegment.addPoint(result.afterVertex, True)
        self.rubberBandSelectedSegment.show()
        
        self.step = 1
        self.next()
        
    def secondEdgeFound(self, candidateLayers, combobox,  result, pointClicked):
        index=combobox.currentIndex()
        self.defaultIndex=index
        self.outputLayer=candidateLayers[index]
        
        self.snappingResultSecondEdge = result
        
        try:self.segmentFinderTool.segmentFound.disconnect() 
        except Exception: pass
        
        self.segmentFinderTool.deactivate()
        
        self.step = 2
        self.next()
        
    def listCandidateLayers(self, onlyEditable=True):
        candidates=[]
        candidateLayers=[]
        defaultIndex=0
        for layer in QgsMapLayerRegistry.instance().mapLayers().values():
            if (layer.type() == QgsMapLayer.VectorLayer and layer.geometryType() == QGis.Line and
                (not onlyEditable or layer.isEditable())):
                candidates.append(layer.name())
                candidateLayers.append(layer)
        sortedCandidates=sorted(enumerate(candidates),key=itemgetter(1))
        candidates=map(itemgetter(1),sortedCandidates)
        candidateLayers=map(lambda x:candidateLayers[x[0]],sortedCandidates)
        for index in range(len(candidateLayers)):
            if candidateLayers[index] == self.layer:
                defaultIndex=index
        return candidates, candidateLayers,defaultIndex
        
   
    def doCenterline(self):
        self.messageBarUtils.showMessage("Centerline", "Running...", duration=0)
        try:
            qDebug("New Centerline")
            
            firstSegment=self._getSegment(self.snappingResultFirstEdge)
            secondSegment=self._getSegment(self.snappingResultSecondEdge)
            endSegments=self._getEndSegments(firstSegment, secondSegment)
            
            # middle of each end segments
            centerlineEndPoint1=QgsPoint((endSegments[0].vertexAt(0).x()+endSegments[0].vertexAt(1).x())/2,
                                         (endSegments[0].vertexAt(0).y()+endSegments[0].vertexAt(1).y())/2)
            centerlineEndPoint2=QgsPoint((endSegments[1].vertexAt(0).x()+endSegments[1].vertexAt(1).x())/2,
                                         (endSegments[1].vertexAt(0).y()+endSegments[1].vertexAt(1).y())/2)
            line=QgsGeometry.fromPolyline([centerlineEndPoint1,centerlineEndPoint2])
            self.outputLayer.beginEditCommand("Centerline")
            feature=QgsFeature()
            feature.initAttributes(self.outputLayer.dataProvider().fields().count())
            feature.setGeometry(line)
            self.outputLayer.addFeature(feature)
            
            self.outputLayer.endEditCommand()
            
            self.iface.mapCanvas().refresh()
            
            self.messageBarUtils.showMessage("Centerline", "The centerline was created successfully", duration=2)
        except Exception as e:
            QgsMessageLog.logMessage(repr(e))
            self.messageBarUtils.showMessage("Centerline", "There was an error performing this command. See QGIS Message log for details", QgsMessageBar.CRITICAL, duration=5)   
            self.outputLayer.destroyEditCommand()
            self.done()
            
        self.resetCenterline()
        self.next()
            
    def _getEndSegments(self, firstSegment, secondSegment):
        candidates1=(QgsGeometry.fromPolyline([firstSegment.vertexAt(0), secondSegment.vertexAt(0)]),
                    QgsGeometry.fromPolyline([firstSegment.vertexAt(1), secondSegment.vertexAt(1)])) 
        candidates2=(QgsGeometry.fromPolyline([firstSegment.vertexAt(0), secondSegment.vertexAt(1)]),
                    QgsGeometry.fromPolyline([firstSegment.vertexAt(1), secondSegment.vertexAt(0)]))
        if candidates1[0].intersects(candidates1[1]):
            return candidates2
        else:
            return candidates1
      
            
    def _getFeature(self, snappingResult):
        fid = snappingResult.snappedAtGeometry
        feature = QgsFeature()
        fiter = snappingResult.layer.getFeatures(QgsFeatureRequest(fid))
        if fiter.nextFeature(feature):
            return feature
        return None 
    
    def _getSegment(self, snappingResult):
        feature = self._getFeature(snappingResult)
        geometry = feature.geometry()
        bv = geometry.vertexAt(snappingResult.beforeVertexNr)
        av = geometry.vertexAt(snappingResult.afterVertexNr)
        return QgsGeometry.fromPolyline([bv,av])
        
    def done(self):
        self.reset()
        self.iface.mapCanvas().unsetMapTool(self)
        
    def enter(self):
        #ignore
        pass
    
    def canvasPressEvent(self, e):
        # use right button instead of clicking on button in message bar
        if e.button() == Qt.RightButton:
            if self.step == 0:
                self.done()
                return
        
        if self.currentMapTool:
            self.currentMapTool.canvasPressEvent(e)

    def canvasReleaseEvent(self, e):
        if self.currentMapTool:
            self.currentMapTool.canvasReleaseEvent(e)

    def canvasMoveEvent(self, e):
        if self.currentMapTool:
            self.currentMapTool.canvasMoveEvent(e)

def sqDistance(pt1, pt2):
    return (pt1.x() - pt2.x())**2 + (pt1.y() - pt2.y())**2