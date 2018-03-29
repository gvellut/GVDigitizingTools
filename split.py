# -*- coding: utf-8 -*-
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *
from messagebarutils import MessageBarUtils
from segmentfindertool import SegmentFinderTool
import math
import vectorlayerutils
  
class SplitDigitizingMode(QgsMapToolEmitPoint):
    def __init__(self, iface):
        self.iface = iface
        QgsMapToolEmitPoint.__init__(self, self.iface.mapCanvas())
        
        self.messageBarUtils = MessageBarUtils(iface)
        
        self.rubberBandSnap = QgsRubberBand(self.iface.mapCanvas())
        self.rubberBandSnap.setColor(QColor(255, 51, 153))
        self.rubberBandSnap.setIcon(QgsRubberBand.ICON_CROSS)
        self.rubberBandSnap.setIconSize(12)
        self.rubberBandSnap.setWidth(3)
        
        self.snapper = QgsMapCanvasSnapper(self.iface.mapCanvas())
        
        self.layer = None
        self.reset()
    
    def setLayer(self, layer):
        self.layer = layer
        
    def reset(self, clearMessages = True):
        self.step = 0
        
        self.rubberBandSnap.reset(QGis.Point)
        
        if clearMessages:
            self.messageBarUtils.removeAllMessages()
        
    def deactivate(self):
        self.reset()
        QgsMapToolEmitPoint.deactivate(self)
        
    def next(self):
        if self.step == 0:
            self.messageBarUtils.showMessage("Split", "Select segment to cut", duration = 0)
        elif self.step == 1:
            self.doSplit()
   
    def doSplit(self):
        self.messageBarUtils.showMessage("Split", "Running...", duration=0)
        try:
            qDebug("New Split")
            self.layer.beginEditCommand("Split")
            
            featureToSplit=self._getFeature(self.snappingResultSplit)
            segmentSplit=self._getSegment(self.snappingResultSplit)
            vertexSplit=self.snappingResultSplit.snappedVertex
            
            # transform snapped vertex
            vertexSplit=self.iface.mapCanvas().mapSettings().mapToLayerCoordinates( self.layer,vertexSplit)
            _,_,vertexSplit=vectorlayerutils.closestSegmentWithContext(vertexSplit, segmentSplit.asPolyline())
            
            newGeometries=self.splitAt(featureToSplit.geometry(),vertexSplit, self.snappingResultSplit.snappedVertexNr)
            
            if len(newGeometries) > 1:
                # change the first one
                self.layer.changeGeometry(featureToSplit.id(), newGeometries[0])
                
                # create new ones for every other geometry
                attrs=featureToSplit.attributes()
                pgidIndex=self.layer.fieldNameIndex("gid")
                newFeature=QgsFeature()
                for indexGeometry in range(1,len(newGeometries)):
                    newFeature.initAttributes(len(attrs))
                    for index in range(len(attrs)):
                        if index <> pgidIndex:
                            newFeature.setAttribute(index, attrs[index]) 
                    newFeature.setGeometry(newGeometries[indexGeometry])
                    self.layer.addFeature(newFeature)
                    
                self.messageBarUtils.showMessage("Split", "The segment was split successfully", duration=2)
            else:
                self.messageBarUtils.showMessage("Split", "The segment was not split",  QgsMessageBar.WARNING, duration=2)
                
            self.layer.endEditCommand()
            
            self.iface.mapCanvas().refresh()
    
        except Exception as e:
            QgsMessageLog.logMessage(repr(e))
            self.messageBarUtils.showMessage("Split", "There was an error performing this command. See QGIS Message log for details", 
                                             QgsMessageBar.CRITICAL, duration=5)   
            self.layer.destroyEditCommand()
            raise  
        finally:
            self.iface.mapCanvas().unsetMapTool(self)
        
    def splitAt(self, geometry, vertex, vertexNr):
        if vertexNr == -1:
            geometry.insertVertex(vertex.x(),vertex.y(),self.snappingResultSplit.afterVertexNr)
            splitIndex=self.snappingResultSplit.afterVertexNr
        else:
            # no need to add a new vertex
            splitIndex=vertexNr
            
        if geometry.isMultipart():
            vertexCount=0
            mp=geometry.asMultiPolyline()
            for index in range(len(mp)):
                p=mp[index]
                if vertexCount+len(p) > splitIndex:
                    relativeSplitIndex=splitIndex-vertexCount
                    splitLine1=p[0:relativeSplitIndex+1]
                    splitLine2=p[relativeSplitIndex:]
                    
                    firstGeometry=mp[0:index]
                    firstGeometry.append(splitLine1)
                    secondGeometry=[splitLine2]
                    secondGeometry.extend(mp[index+1:])
                    
                    qDebug(repr(firstGeometry))
                    
                    return (QgsGeometry.fromMultiPolyline(firstGeometry),
                            QgsGeometry.fromMultiPolyline(secondGeometry))
                else:
                    vertexCount+=len(p)
        else:
            p=geometry.asPolyline()
            # a vertex has been added so splitVertex has index afterVertexNr
            return (QgsGeometry.fromPolyline(p[0:splitIndex+1]),
                    QgsGeometry.fromPolyline(p[splitIndex:]))
    
    def _getFeature(self, snappingResult):
        fid = snappingResult.snappedAtGeometry
        feature = QgsFeature()
        fiter = self.layer.getFeatures(QgsFeatureRequest(fid))
        if fiter.nextFeature(feature):
            return feature
        return None 
    
    def _getSegment(self, snappingResult):
        feature = self._getFeature(snappingResult)
        geometry = feature.geometry()
        bv = geometry.vertexAt(snappingResult.beforeVertexNr)
        av = geometry.vertexAt(snappingResult.afterVertexNr)
        return QgsGeometry.fromPolyline([bv,av])
    
    def enter(self):
        #ignore
        pass
    
    def canvasPressEvent(self, e):
        pass
   
    def canvasReleaseEvent(self, e):
        pos = QPoint(e.pos().x(), e.pos().y())
        result = self.snap(pos)
        if result != []:
            self.snappingResultSplit = result[0]
            self.step = 1
            self.next()
            
    def canvasMoveEvent(self, e):
        pos = QPoint(e.pos().x(), e.pos().y())
        result = self.snap(pos)
        self.rubberBandSnap.reset(QGis.Point)
        if result != []:
            vertex=result[0].snappedVertex
            if result[0].snappedVertexNr == -1:
                segment=self._getSegment(result[0])
                vertex=self.iface.mapCanvas().mapSettings().mapToLayerCoordinates( self.layer, vertex)
                _,_,vertex=vectorlayerutils.closestSegmentWithContext(vertex, segment.asPolyline())
                vertex=self.iface.mapCanvas().mapSettings().layerToMapCoordinates(self.layer,vertex)
            self.rubberBandSnap.addPoint(vertex, True)
          
    def snap(self, pos):
        (_, result) = self.snapper.snapToCurrentLayer(pos, QgsSnapper.SnapToVertexAndSegment)
        return result

def sqDistance(pt1, pt2):
    return (pt1.x() - pt2.x())**2 + (pt1.y() - pt2.y())**2