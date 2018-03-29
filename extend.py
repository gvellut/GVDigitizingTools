# -*- coding: utf-8 -*-
# Import the PyQt and QGIS libraries
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *
from extendutils import ExtendUtils
from messagebarutils import MessageBarUtils
from segmentfindertool import SegmentFinderTool
import vectorlayerutils
import math
import constants

class ExtendDigitizingMode(QgsMapToolEmitPoint):
    def __init__(self, iface):
        self.iface = iface
        QgsMapToolEmitPoint.__init__(self, self.iface.mapCanvas())
        
        self.messageBarUtils = MessageBarUtils(iface)
        
        self.segmentFinderTool = SegmentFinderTool(self.iface.mapCanvas())
        self.rubberBandBoundary = QgsRubberBand(self.iface.mapCanvas())
        self.rubberBandBoundary.setColor(QColor(255, 0, 0))
        self.rubberBandBoundary.setWidth(2)

        self.layer = None
        self.reset()
    
    def setLayer(self, layer):
        self.layer = layer
        
    def reset(self, clearMessages = True):
        self.step = 0
        self.snappingResultBoundaryEdge = None
        self.snappingResultExtendEdge = None
        self.cachedSpatialIndex = None
        
        self.rubberBandBoundary.reset(QGis.Line)
        
        try: self.segmentFinderTool.segmentFound.disconnect()
        except Exception: pass
        
        if clearMessages:
            self.messageBarUtils.removeAllMessages()
        
    def resetExtend(self, full=False):
        if full:
            self.reset(False)
        else:
            # jsut the last step
            self.step = 1
            self.snappingResultExtendEdge = None
    
    def deactivate(self):
        self.reset()
        QgsMapToolEmitPoint.deactivate(self)
        
    def next(self):
        if self.step == 0:
            # always starts at this step: test if there is a selection
            if self.layer.selectedFeatureCount() > 0:
                # next
                self.step = 1
                self.next()
                return
            self.messageBarUtils.showButton("Extend", "Select boundary edge", "Use full layer", buttonCallback=self.useFullLayer)
            self.currentMapTool = self.segmentFinderTool
            self.segmentFinderTool.segmentFound.connect(self.boundaryEdgeFound)
        elif self.step == 1:
            self.messageBarUtils.showButton("Extend", "Select edge to extend", "Done", buttonCallback=self.done)
            self.currentMapTool = self.segmentFinderTool
            self.segmentFinderTool.segmentFound.connect(self.extendEdgeFound)
        elif self.step == 2:
            self.doExtend()
         
    def boundaryEdgeFound(self, result, pointClicked):
        self.snappingResultBoundaryEdge = result
        self.segmentFinderTool.segmentFound.disconnect(self.boundaryEdgeFound)
        self.segmentFinderTool.deactivate()
        
        self.rubberBandBoundary.reset(QGis.Line)
        self.rubberBandBoundary.addPoint(result.beforeVertex)
        self.rubberBandBoundary.addPoint(result.afterVertex, True)
        self.rubberBandBoundary.show()
        
        self.step = 1
        self.next()
        
    def extendEdgeFound(self, result, pointClicked):
        self.snappingResultExtendEdge = result
        self.segmentFinderTool.segmentFound.disconnect(self.extendEdgeFound)
        self.segmentFinderTool.deactivate()
        
        transform = QgsCoordinateTransform(self.iface.mapCanvas().mapSettings().destinationCrs(), self.layer.crs())
        g = QgsGeometry.fromPoint(pointClicked)
        g.transform(transform)
        self.pointExtend = g.asPoint()
        
        self.step = 2
        self.next()
   
    def doExtend(self):
        self.messageBarUtils.showMessage("Extend", "Running...", duration=0)
        extendUtils = ExtendUtils(self.iface)
        try:
            featureExtend = self._getFeature(self.snappingResultExtendEdge)
            geometryExtend = featureExtend.geometry()
            bvExtend = geometryExtend.vertexAt(self.snappingResultExtendEdge.beforeVertexNr)
            avExtend = geometryExtend.vertexAt(self.snappingResultExtendEdge.afterVertexNr)
            
            vertexNrToMove = extendUtils.vertexIndexToMove(bvExtend, avExtend, self.snappingResultExtendEdge, 
                                                   self.pointExtend, mustExtend=False)
            vertexToMove = geometryExtend.vertexAt(vertexNrToMove)
            
            testRay = self.getTestRayForExtend(extendUtils, geometryExtend, bvExtend, avExtend, vertexNrToMove)
            # 3 cases: selection on layer, whole layer, cutting edge
            if self.layer.selectedFeatureCount() > 0 or not self.snappingResultBoundaryEdge:
                # use same strategy for both
                pointIntersection, alreadyNearEdge  = self.getExtendInformationFromLayer(extendUtils, testRay, vertexToMove)
            else:
                # no ambiguity here
                pointIntersection, alreadyNearEdge = self.getExtendInformationFromSnappedBoundaryEdge(extendUtils, testRay, vertexToMove)
            
            if alreadyNearEdge:
                self.messageBarUtils.showMessage("Extend", "Nothing done: Already at boundary edge", QgsMessageBar.WARNING, duration=2)
            elif pointIntersection:
                if self.cachedSpatialIndex:
                    self.cachedSpatialIndex.deleteFeature(featureExtend)
                    
                fid = featureExtend.id()
                geometryExtend.moveVertex(pointIntersection.x(), pointIntersection.y(), vertexNrToMove)
                self.layer.beginEditCommand("Extend")
                self.layer.changeGeometry(fid, geometryExtend)
                if self.cachedSpatialIndex:
                    self.cachedSpatialIndex.insertFeature(featureExtend)
                self.layer.endEditCommand()
                
                self.iface.mapCanvas().refresh()  
                
                self.messageBarUtils.showMessage("Extend", "The segment was extended successfully", duration=2)
            else:
                self.messageBarUtils.showMessage("Extend", "Nothing done: No suitable boundary edge", QgsMessageBar.WARNING, duration=2)
        except Exception as e:
            QgsMessageLog.logMessage(repr(e))
            self.messageBarUtils.showMessage("Trim", "There was an error performing this command. See QGIS Message log for details", QgsMessageBar.CRITICAL, duration=5)            
    
        # select another edge to extend
        self.resetExtend()
        self.next()
        
    def _getFeature(self, snappingResult):
        fid = snappingResult.snappedAtGeometry
        feature = QgsFeature()
        fiter = self.layer.getFeatures(QgsFeatureRequest(fid))
        if fiter.nextFeature(feature):
            return feature
        return None
    
    def buildSpatialIndex(self):
        if not self.cachedSpatialIndex:
            # Build the spatial index for faster lookup.
            index = QgsSpatialIndex()
            for f in vectorlayerutils.features(self.layer):
                index.insertFeature(f)
            self.cachedSpatialIndex = index
            
    def isNearEdgeInLayer(self, point, distance):
        bufferGeometry = QgsGeometry.fromPoint(point).buffer(distance, 2)
        fids = self.cachedSpatialIndex.intersects(bufferGeometry.boundingBox())
        for fid in fids:
            if fid == self.snappingResultExtendEdge.snappedAtGeometry:
                continue
            feature = self.layer.getFeatures(QgsFeatureRequest(fid)).next()
            geometryTest = feature.geometry()
            if bufferGeometry.intersects(geometryTest):
                return True
        return False
        
    def getExtendInformationFromLayer(self, extendUtils, testRay, vertexToMove):
        self.buildSpatialIndex()
            
        if self.isNearEdgeInLayer(vertexToMove, constants.TOLERANCE_DEGREE):
            return (None,True) 
            
        # get segment
        fids = self.cachedSpatialIndex.intersects(testRay.boundingBox())
        candidates = []
        for fid in fids:
            if fid == self.snappingResultExtendEdge.snappedAtGeometry:
                continue
            feature = self.layer.getFeatures(QgsFeatureRequest(fid)).next()
            geometryTest = feature.geometry()
            if testRay.intersects(geometryTest):
                candidates.extend(vectorlayerutils.segmentIntersectionPoint(geometryTest, testRay))
                
        # extend as short as possible among the candidate intersection points
        if len(candidates) > 0:
            distancesToVertexToMove = map(lambda x: self.sqDistance(vertexToMove, x), candidates)
            closestIndices = sorted(range(len(distancesToVertexToMove)),key=lambda i:distancesToVertexToMove[i])
            return (candidates[closestIndices[0]], False)
        
        return (None, False)
    
    def isNearSingleEdge(self, point, edge, distance):
        bufferGeometry = QgsGeometry.fromPoint(point).buffer(distance, 2)
        return edge.intersects(bufferGeometry)
                    
    def getExtendInformationFromSnappedBoundaryEdge(self, extendUtils, testRay, vertexToMove):
        featureBoundary = self._getFeature(self.snappingResultBoundaryEdge)
        geometryBoundary = featureBoundary.geometry()
        bvBoundary = geometryBoundary.vertexAt(self.snappingResultBoundaryEdge.beforeVertexNr)
        avBoundary = geometryBoundary.vertexAt(self.snappingResultBoundaryEdge.afterVertexNr)
        edgeBoundary = QgsGeometry.fromPolyline([bvBoundary,avBoundary])
        
        if self.isNearSingleEdge(vertexToMove, edgeBoundary, constants.TOLERANCE_DEGREE):
            return (None,True)
        
        if testRay.intersects(edgeBoundary):
            # only one possible intersection point (2 edges)
            pointIntersection = vectorlayerutils.segmentIntersectionPoint(testRay, edgeBoundary)
            if pointIntersection:
                pointIntersection = pointIntersection[0]
            return (pointIntersection, False)
        
        return (None, False)
            
    def getTestRayForExtend(self, extendUtils, geometryExtend, bvExtend, avExtend, vertexNrToMove):
        # Create a segment that goes away from the edgeExtend, starting at vertexNrToMove
        # and ending at the bounding box of the layer
        if vertexNrToMove == self.snappingResultExtendEdge.afterVertexNr:
            baseVertex = avExtend
            # direction towards which the extension will be performed
            vectorDirection = [bvExtend, avExtend]
        else:
            baseVertex = bvExtend
            vectorDirection = [avExtend,bvExtend]
        
        boundingBox = self.layer.extent()
        topLeft = QgsPoint(boundingBox.xMinimum(),boundingBox.yMaximum())
        topRight = QgsPoint(boundingBox.xMaximum(),boundingBox.yMaximum())
        bottomRight = QgsPoint(boundingBox.xMaximum(),boundingBox.yMinimum())
        bottomLeft = QgsPoint(boundingBox.xMinimum(),boundingBox.yMinimum())
        
        topIntersection = extendUtils.intersectionPoint(bvExtend, avExtend, topLeft, topRight)
        # check that the vector from baseVertex to that point is in the same direction as
        # vector direction
        if topIntersection and self.dp(vectorDirection[0], vectorDirection[1], baseVertex, topIntersection) > 0:
            return QgsGeometry.fromPolyline([baseVertex, topIntersection])
        
        rightIntersection = extendUtils.intersectionPoint(bvExtend, avExtend, topRight, bottomRight)
        if rightIntersection and self.dp(vectorDirection[0], vectorDirection[1], baseVertex, rightIntersection) > 0:
            return QgsGeometry.fromPolyline([baseVertex, rightIntersection])
        
        bottomIntersection = extendUtils.intersectionPoint(bvExtend, avExtend, bottomRight, bottomLeft)
        if bottomIntersection and self.dp(vectorDirection[0], vectorDirection[1], baseVertex, bottomIntersection) > 0:
            return QgsGeometry.fromPolyline([baseVertex, bottomIntersection])
        
        leftIntersection = extendUtils.intersectionPoint(bvExtend, avExtend, bottomLeft, topLeft)
        if leftIntersection and self.dp(vectorDirection[0], vectorDirection[1], baseVertex, leftIntersection) > 0:
            return QgsGeometry.fromPolyline([baseVertex, leftIntersection])
        
    
    def dp(self, pt11, pt12, pt21, pt22):
        return (pt12.x() - pt11.x()) * (pt22.x() - pt21.x()) + (pt12.y() - pt11.y()) * (pt22.y() - pt21.y())
    
    def sqDistance(self, pt1, pt2):
        return (pt1.x() - pt2.x())**2 + (pt1.y() - pt2.y())**2
    
    def useFullLayer(self):
        self.snappingResultBoundaryEdge = None
        self.segmentFinderTool.segmentFound.disconnect(self.boundaryEdgeFound)
        self.segmentFinderTool.deactivate()
        
        self.step = 1
        self.next()
    
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
                self.useFullLayer()
                return
            elif self.step == 1:
                self.resetExtend(True)
                self.next()
                return
        
        if self.currentMapTool:
            self.currentMapTool.canvasPressEvent(e)

    def canvasReleaseEvent(self, e):
        if self.currentMapTool:
            self.currentMapTool.canvasReleaseEvent(e)

    def canvasMoveEvent(self, e):
        if self.currentMapTool:
            self.currentMapTool.canvasMoveEvent(e)
 
