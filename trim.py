# -*- coding: utf-8 -*-
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *
from messagebarutils import MessageBarUtils
from segmentfindertool import SegmentFinderTool
import vectorlayerutils  
import constants
import sys
  
class TrimDigitizingMode(QgsMapToolEmitPoint):
    def __init__(self, iface):
        self.iface = iface
        QgsMapToolEmitPoint.__init__(self, self.iface.mapCanvas())
        
        self.messageBarUtils = MessageBarUtils(iface)
        
        self.segmentFinderTool = SegmentFinderTool(self.iface.mapCanvas())
        self.rubberBandCutting = QgsRubberBand(self.iface.mapCanvas())
        self.rubberBandCutting.setColor(QColor(255, 0, 0))
        self.rubberBandCutting.setWidth(2)
        
        self.layer = None
        self.reset()
    
    def setLayer(self, layer):
        self.layer = layer
        
    def reset(self, clearMessages = True):
        self.step = 0
        self.snappingResultCuttingEdge = None
        self.snappingResultTrim = None
        self.cachedSpatialIndex = None
        
        self.rubberBandCutting.reset(QGis.Line)
        
        try:self.segmentFinderTool.segmentFound.disconnect()
        except Exception: pass
        
        if clearMessages:
            self.messageBarUtils.removeAllMessages()
            
    def resetTrim(self):
        self.step = 1
        self.snappingResultTrim = None
        
    def deactivate(self):
        self.reset()
        QgsMapToolEmitPoint.deactivate(self)
        
    def next(self):
        if self.step == 0:
                        
            # alwways starts at this step: test if there is a selection
            if self.layer.selectedFeatureCount() > 0:
                # next
                self.step = 1
                self.next()
                return
            self.messageBarUtils.showButton("Trim", "Select cutting edge", "Use full layer", buttonCallback=self.useFullLayer)
            self.currentMapTool = self.segmentFinderTool
            self.segmentFinderTool.segmentFound.connect(self.cuttingEdgeFound)
        elif self.step == 1:
            self.messageBarUtils.showButton("Trim", "Select segment to trim","Done",buttonCallback=self.done)
            self.currentMapTool = self.segmentFinderTool
            self.segmentFinderTool.segmentFound.connect(self.trimEdgeFound)
        elif self.step == 2:
            self.doTrim()
         
    def cuttingEdgeFound(self, result, pointClicked):
        self.snappingResultCuttingEdge = result
        self.segmentFinderTool.segmentFound.disconnect(self.cuttingEdgeFound)
        self.segmentFinderTool.deactivate()
        
        self.rubberBandCutting.reset(QGis.Line)
        self.rubberBandCutting.addPoint(result.beforeVertex)
        self.rubberBandCutting.addPoint(result.afterVertex, True)
        self.rubberBandCutting.show()
        
        self.step = 1
        self.next()
        
    def trimEdgeFound(self, result, pointClicked):
        self.snappingResultTrim = result
        self.segmentFinderTool.segmentFound.disconnect(self.trimEdgeFound)
        self.segmentFinderTool.deactivate()
        
        transform = QgsCoordinateTransform(self.iface.mapCanvas().mapSettings().destinationCrs(), self.layer.crs())
        g = QgsGeometry.fromPoint(pointClicked)
        g.transform(transform)
        self.pointTrim = g.asPoint()
        
        self.step = 2
        self.next()
   
    def doTrim(self):
        self.messageBarUtils.showMessage("Trim", "Running...", duration=0)
        trimUtils = TrimUtils(self.iface)
        try:
            qDebug("New Trim")
            # 3 cases: selection on layer, whole layer, cutting edge
            if self.layer.selectedFeatureCount() > 0 or not self.snappingResultCuttingEdge:
                # use same strategy for both
                indexReferenceIntersection, pointIntersections  = self.getTrimmingInformationFromLayer(trimUtils)
            else:
                # no ambiguity here
                indexReferenceIntersection, pointIntersections = self.getTrimmingInformationFromSnappedGeometry(trimUtils)
                
            if indexReferenceIntersection != None:
                featureTrim = self._getFeature(self.snappingResultTrim)
                geometryTrim = featureTrim.geometry()
            
                parts, unconcernedParts = trimUtils.removeVertices(geometryTrim, indexReferenceIntersection, pointIntersections, 
                                                  self.snappingResultTrim.afterVertexNr, self.pointTrim)
                
                parts = self.cleanupTrimmedParts(parts)
                if len(parts) > 0:
                    if unconcernedParts:
                        parts.extend(unconcernedParts)
                    
                    # replace geometry
                    self.layer.beginEditCommand("Trim")
                    
                    # geometry updated => remove from index (readded very soon)
                    if self.cachedSpatialIndex:
                        self.cachedSpatialIndex.deleteFeature(featureTrim)
                    
                    # by default create a multipart geometry (unless not supported by data provider)
                    # for ex PostGIS layer can be constrained to be multipart
                    # some data types can have mixed multi/single (ex shp)
                    if (geometryTrim.isMultipart() or len(parts) > 1) and QGis.isMultiType(self.layer.dataProvider().geometryType()) :
                        qDebug("Multipart")
                        geometryTrim = QgsGeometry.fromMultiPolyline(map(lambda x:x.asPolyline(),parts))
                        self.layer.changeGeometry(featureTrim.id(), geometryTrim)
                        # for some reason, the line above makes it so the feature cannot be deleted from the index the next time
                        featureTrim.setGeometry(geometryTrim)
                        if self.cachedSpatialIndex:
                            self.cachedSpatialIndex.insertFeature(featureTrim)
                    else:
                        qDebug("Singlepart")
                        self.layer.deleteFeature(featureTrim.id())
                        # create a new feature for each part (so still single part geometries)
                        for part in parts:
                            featureTrim.setGeometry(part)
                            self.layer.addFeature(featureTrim)
                            if self.cachedSpatialIndex:
                                self.cachedSpatialIndex.insertFeature(featureTrim)
                        
                    self.layer.endEditCommand()
                    
                    self.iface.mapCanvas().refresh()
            
                    self.messageBarUtils.showMessage("Trim", "The segment was trimmed successfully", duration=2)
                else:
                    self.messageBarUtils.showMessage("Trim", "Nothing done: Trimming would create an invalid geometry", QgsMessageBar.WARNING, duration=2)
            else:
                self.messageBarUtils.showMessage("Trim", "Nothing done: The geometries are not intersecting", QgsMessageBar.WARNING, duration=2)
        except Exception as e:
            QgsMessageLog.logMessage(repr(e))
            self.messageBarUtils.showMessage("Trim", "There was an error performing this command. See QGIS Message log for details", QgsMessageBar.CRITICAL, duration=5)   
            self.layer.destroyEditCommand()
            self.done()
            
        self.resetTrim()
        self.next()
            
    def cleanupTrimmedParts(self, parts):
        return filter(lambda x: x and x.length() > constants.TOLERANCE_DEGREE*2, parts)
    
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
    
    def getTrimmingInformationFromSnappedGeometry(self, trimUtils):   
        edgeCuttingEdge = self._getSegment(self.snappingResultCuttingEdge)
        featureTrim = self._getFeature(self.snappingResultTrim)
        geometryTrim = featureTrim.geometry()
        
        bufferGeometryTrim = geometryTrim.buffer(constants.TOLERANCE_DEGREE, 2)
        
        if bufferGeometryTrim.intersects(edgeCuttingEdge):
            candidates = trimUtils.intersectionPointWithTolerance(edgeCuttingEdge, bufferGeometryTrim, geometryTrim)
            
        if len(candidates) > 0:
            index = self.indexOfClosestIntersection(candidates)
            return index, candidates
        return (None, None)
    
    def buildSpatialIndex(self):
        if not self.cachedSpatialIndex:
            # Build the spatial index for faster lookup.
            index = QgsSpatialIndex()
            for f in vectorlayerutils.features(self.layer):
                index.insertFeature(f)
            self.cachedSpatialIndex = index 
    
    def getTrimmingInformationFromLayer(self, trimUtils):
        try:
            self.buildSpatialIndex()
                
            # get geometry
            featureTrim = self._getFeature(self.snappingResultTrim)
            geometryTrim = featureTrim.geometry()
            
            # use buffered geometry to solve unexact geoemtries because of limited floating 
            # precision (point on a line never exactly on the line) 
            # (sometimes no intersection is present when there should be)
            bufferGeometryTrim = geometryTrim.buffer(constants.TOLERANCE_DEGREE, 2)
            
            fids = self.cachedSpatialIndex.intersects(bufferGeometryTrim.boundingBox())
            if  len(fids) > 0:
                candidates = []
                for fid in fids:
                    if fid == self.snappingResultTrim.snappedAtGeometry:
                        continue
                    features = self.layer.getFeatures(QgsFeatureRequest(fid))
                    feature = features.next()
                    geometryTest = feature.geometry()
                    if bufferGeometryTrim.intersects(geometryTest):
                        pointIntersection = trimUtils.intersectionPointWithTolerance(geometryTest, bufferGeometryTrim, geometryTrim)
                        candidates.extend(pointIntersection)
                        
                if len(candidates) > 0:
                    index = self.indexOfClosestIntersection(candidates)
                    return index, candidates
                
            return (None, None)
        except StopIteration:
            # index is invalid maybe because undo was performed: force rebuild
            # and relaunch
            self.cachedSpatialIndex = None
            return self.getTrimmingInformationFromLayer(trimUtils)
    
    def indexOfClosestIntersection(self, candidates):
        distancesToSnappedTrimPoint = map(lambda x: sqDistance(self.pointTrim, x), candidates)
        closestIndices = sorted(range(len(distancesToSnappedTrimPoint)),key=lambda i:distancesToSnappedTrimPoint[i])
        return closestIndices[0]
    
    def useFullLayer(self):
        self.snappingResultCuttingEdge = None
        # cleanup
        self.segmentFinderTool.segmentFound.disconnect(self.cuttingEdgeFound)
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

# TODO add GeometryUtils with common geometric checks
class TrimUtils:
    
    def __init__(self, iface):
        self.iface = iface
        self.canvas = self.iface.mapCanvas()
        
    def intersectionPoint(self, geometryCuttingEdge, geometryTrim):
        intersectionPoint = geometryCuttingEdge.intersection(geometryTrim)
        if not intersectionPoint or intersectionPoint.type() != QGis.Point:
            return []
        if intersectionPoint.isMultipart():
            # list of points
            point = intersectionPoint.asMultiPoint()
        else:
            # make it a list of points
            point = [intersectionPoint.asPoint()]
        return point
    
    def intersectionPointWithTolerance(self, geometryCuttingEdge, bufferGeometryTrim, geometryTrim):
        # bufferGeometryTrim incorporates the tolerance
        intersectionLine = geometryCuttingEdge.intersection(bufferGeometryTrim)
        if not intersectionLine or intersectionLine.type() != QGis.Line:
            return []
        if intersectionLine.isMultipart():
            qDebug("ToleranceMulti")
            # list of points
            # intersection very small: take any of the vertices and get closest to geometryTrim
            intersectionPoint = []
            for line in intersectionLine.asMultiPolyline():
                intersectionPoint.append(self.analyseIntersectionWithTolerance(QgsGeometry.fromPolyline(line), geometryTrim))
        else:
            qDebug("ToleranceSingle")
            # make it a list of points
            intersectionPoint = [self.analyseIntersectionWithTolerance(intersectionLine, geometryTrim)]
            
        return intersectionPoint
    
    def analyseIntersectionWithTolerance(self, line, geometryTrim):
        # close up qnd check that it intersects the geometry itself:
        intersectionPoint = line.intersection(geometryTrim)
        if intersectionPoint and intersectionPoint.type() == QGis.Point:
            # use that
            if intersectionPoint.isMultipart():
                # only take the first one because the other points would be very close anyway (within tolerance)
                return intersectionPoint.asMultiPoint()[0]
            else:
                return intersectionPoint.asPoint()
        else:
            qDebug("Tolerance")
            # get the vertex of the geometryTrim closest to the intersection (line)
            # one of the points of the intersection will be the same as one of the points of the 
            # geometryTrim
            
            if geometryTrim.isMultipart():
                polylines=geometryTrim.asMultiPolyline()
            else:
                polylines=[geometryTrim.asPolyline()]
                
            line=line.asPolyline()
            
            minDist=sys.float_info.max
            minPoint=None
            for polyline in polylines:
                for point in line:
                    dist,_,distPoint = vectorlayerutils.closestSegmentWithContext(point, polyline, 0)
                    if dist < minDist:
                        minDist=dist
                        minPoint=distPoint
                             
            return minPoint

    def removeVertices(self, geometryTrim, indexReferenceIntersection, pointIntersections, 
                       snapAfter, snapPoint):
        
        # first we consider all parts (so we get the vertexNrAfters for the whole geoemtry)
        # cache for later (in case of multiple intersections)
        if geometryTrim.isMultipart():
            polylineTrim=vectorlayerutils.flattenMultiPolyline(geometryTrim.asMultiPolyline())
        else:
            polylineTrim=geometryTrim.asPolyline()
        vertexNrAfters = map(lambda x:self._findAfterVertexNr(x, polylineTrim), pointIntersections)
        
        pointIntersection = pointIntersections[indexReferenceIntersection]
        vertexNrAfter = vertexNrAfters[indexReferenceIntersection]
        
        # if multipart find the parts unconcerned with trimming:
        # check which part is the one containing the referenceIntersection
        # "throw away" the others
        if geometryTrim.isMultipart():
            multipolyline=geometryTrim.asMultiPolyline()
            unconcernedParts=[]
            index = 0
            for polyline in multipolyline:
                if vertexNrAfter >= index and vertexNrAfter < index+len(polyline):
                    # only this part will be considered for trimming
                    polylineTrim=polyline
                    # throw away all the intersections on parts not concerned by trimming
                    indicesToKeep=filter(lambda x: vertexNrAfters[x] >=index and vertexNrAfters[x]<index+len(polyline), 
                                         range(len(vertexNrAfters)))
                    
                    # updates the indices so coherent with updated arrays and geometries
                    vertexNrAfters=[vertexNrAfters[i]-index for i in indicesToKeep]
                    pointIntersections=[pointIntersections[i] for i in indicesToKeep]
                    indexReferenceIntersection=pointIntersections.index(pointIntersection)
                    vertexNrAfter=vertexNrAfters[indexReferenceIntersection]
                    # rebase
                    snapAfter -= index
                else:
                    unconcernedParts.append(polyline)
                index += len(polyline)
        else:
            polylineTrim=geometryTrim.asPolyline()
            unconcernedParts=[]
            
        if vertexNrAfter == snapAfter:
            p1 = QgsGeometry.fromPoint(pointIntersection)
            p2 = QgsGeometry.fromPoint(snapPoint)
            g = QgsGeometry.fromPoint(polylineTrim[vertexNrAfter])
            
            # cut in the after direction if distance of snap point to afterVertex
            # is smaller than distance of intersection point to afterVertexs
            cutAfterIntersection = p1.distance(g) > p2.distance(g)
            qDebug("Case1 ")
        else:
            cutAfterIntersection = snapAfter > vertexNrAfter
            qDebug("Case2")
        
        # cache distances
        distances = [sqDistance(x[1], polylineTrim[vertexNrAfters[x[0]]]) for x in enumerate(pointIntersections)]
        
        # list of indices (in the pointIntersections list) sorted in ascending vertexNr on the part of geoemtryTrim 
        # that contains the reference intersection
        sortedIndexPointIntersections = sorted(range(len(pointIntersections)),
                                                     cmp=self._comparePointsOnGeometry(vertexNrAfters, distances))
        indexOfReferenceIntersectionPoint = sortedIndexPointIntersections.index(indexReferenceIntersection)
        if cutAfterIntersection:
            indexStopCut = indexOfReferenceIntersectionPoint + 1
            stopCut = indexStopCut < len(sortedIndexPointIntersections)          
        else:
            indexStopCut = indexOfReferenceIntersectionPoint - 1
            stopCut = indexStopCut >= 0
            
        polylineTrim.insert(vertexNrAfter, QgsPoint(pointIntersection.x(), pointIntersection.y()))
        if stopCut:
            pointStopCut = pointIntersections[sortedIndexPointIntersections[indexStopCut]]
            vertexNrAfterForStopCut = vertexNrAfters[sortedIndexPointIntersections[indexStopCut]]
            if cutAfterIntersection:
                # + 1 because 1 vertex was just added (at referencePointIntersection)
                vertexNrAfterForStopCut += 1
            polylineTrim.insert(vertexNrAfterForStopCut, QgsPoint(pointStopCut.x(), pointStopCut.y()))
        
        # assume only one part originally
        if cutAfterIntersection:
            # intersection point hqs been qdded (with index vertexNrAfter)
            # remove everything after it
            if stopCut:
                # vertexStopCut is the index of the stopCut point just added
                parts = [polylineTrim[0:vertexNrAfter+1], polylineTrim[vertexNrAfterForStopCut:]]
            else:
                parts = [polylineTrim[0:vertexNrAfter+1]]
        else:
            # intersection point has been added (with index vertexNrAfter)
            # remove everything before it
            if stopCut:
                # + 1 for second part because vertex for StopCut has been added before it
                parts = [polylineTrim[0:vertexNrAfterForStopCut+1], polylineTrim[vertexNrAfter+1:]]
            else:
                parts = [polylineTrim[vertexNrAfter:]]
        
        return map(lambda x:QgsGeometry.fromPolyline(x), parts), map(lambda x:QgsGeometry.fromPolyline(x), unconcernedParts)
    
    def _comparePointsOnGeometry(self,vertexNrAfters, distances):
        def compare(a,b):
            avnrA = vertexNrAfters[a]
            avnrB = vertexNrAfters[b]
            if avnrA > avnrB:
                return 1
            if avnrA < avnrB:
                return -1
            # if here: a and b are on the same segment:
            # compute distance to afterVertex => furthest will be before
            distA = distances[a]
            distB = distances[b]
            if distA > distB:
                # A is before A
                return -1
            if distA < distB:
                return 1
            return 0
        return compare
    
    def _findAfterVertexNr(self, point, polyline):
        _, afterVertexNr,_ = vectorlayerutils.closestSegmentWithContext(point, polyline)
        return afterVertexNr
        
    def extractAsSingleSegments(self, geom):
        segments = []
        if geom.isMultipart():
            multi = geom.asMultiPolyline()
            for polyline in multi:
                segments.extend(self.getPolylineAsSingleSegments(polyline))
        else:
            segments.extend(self.getPolylineAsSingleSegments(
                    geom.asPolyline()))
        return segments

    def getPolylineAsSingleSegments(self, polyline):
        segments = []
        for i in range(len(polyline) - 1):
            ptA = polyline[i]
            ptB = polyline[i + 1]
            segment = QgsGeometry.fromPolyline([ptA, ptB])
            segments.append(segment)
        return segments
    
def sqDistance(pt1, pt2):
    return (pt1.x() - pt2.x())**2 + (pt1.y() - pt2.y())**2