# -*- coding: utf-8 -*-
# Import the PyQt and QGIS libraries
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
from extendutils import ExtendUtils
import processing
import tempfile
import shutil
import os
  
class CenterlineAdvancedDigitizingMode(QgsMapToolEmitPoint):
    def __init__(self, iface):
        self.iface = iface
        QgsMapToolEmitPoint.__init__(self, self.iface.mapCanvas())
        
        self.messageBarUtils = MessageBarUtils(iface)
        self.segmentFinderTool = SegmentFinderTool(self.iface.mapCanvas())
        
        # just needs to rubberbands (when selecting 2nd segment, replaced by selectedLine or
        # hidden)
        self.rubberBandSelectedSegment = QgsRubberBand(self.iface.mapCanvas())
        self.rubberBandSelectedSegment.setColor(QColor(255, 0, 0))
        self.rubberBandSelectedSegment.setWidth(2)
        
        self.rubberBandSelectedLine = QgsRubberBand(self.iface.mapCanvas())
        self.rubberBandSelectedLine.setColor(QColor(255, 0, 0))
        self.rubberBandSelectedLine.setWidth(2)
        
        self.defaultIndex=None
        self.layer = None
        self.reset()
    
    def setLayer(self, layer):
        self.layer = layer
        
    def reset(self, clearMessages = True):
        self.step = 0
        self.snappingResults=[]
        self.snappingPointsClicked=[]
        self.subPolylines=[]
        self.defaultIndex=None
        self.orderSelection=False
        
        self.rubberBandSelectedSegment.reset(QGis.Line)
        self.rubberBandSelectedLine.reset(QGis.Line)
        
        try:self.segmentFinderTool.segmentFound.disconnect()
        except Exception: pass
        
        if clearMessages:
            self.messageBarUtils.removeAllMessages()
            
    def resetCenterline(self):
        self.step = 0
        self.snappingResults=[]
        self.snappingPointsClicked=[]
        self.subPolylines=[]
        self.rubberBandSelectedSegment.reset(QGis.Line)
        self.rubberBandSelectedLine.reset(QGis.Line)
        
        try:self.segmentFinderTool.segmentFound.disconnect()
        except Exception: pass
        
    def deactivate(self):
        self.reset()
        QgsMapToolEmitPoint.deactivate(self)
        
    def next(self):
        if self.step == 0:
            self.messageBarUtils.showButton("Centerline", "Select starting segment of first line", "Done", buttonCallback=self.done)
            _,candidateLayers,_=self.listCandidateLayers(onlyEditable=False)
            self.segmentFinderTool.layers=candidateLayers
            self.currentMapTool = self.segmentFinderTool
            self.segmentFinderTool.segmentFound.connect(self.edgeFound)
        elif self.step == 1:
            self.messageBarUtils.showMessage("Centerline", "Select end segment of first line",  duration=0)
            _,candidateLayers,_=self.listCandidateLayers(onlyEditable=False)
            self.segmentFinderTool.layers=candidateLayers
            self.currentMapTool = self.segmentFinderTool
            self.segmentFinderTool.segmentFound.connect(self.edgeFound)
        elif self.step == 2:
            self.messageBarUtils.showMessage("Centerline", "Select starting segment of second line",  duration=0)
            _,candidateLayers,_=self.listCandidateLayers(onlyEditable=False)
            self.segmentFinderTool.layers=candidateLayers
            self.currentMapTool = self.segmentFinderTool
            self.segmentFinderTool.segmentFound.connect(self.edgeFound)
        elif self.step == 3:
            candidates, candidateLayers, defaultIndex=self.listCandidateLayers(onlyEditable=False)
            if self.defaultIndex <> None and defaultIndex < len(candidateLayers):
                defaultIndex=self.defaultIndex
            _,combobox=self.messageBarUtils.showCombobox("Centerline", "Select end segment of second line", candidates, defaultIndex)
            self.segmentFinderTool.layers=candidateLayers
            self.currentMapTool = self.segmentFinderTool
            self.segmentFinderTool.segmentFound.connect(partial(self.lastEdgeFound, candidateLayers, combobox))
        elif self.step == 4:
            self.doCenterline()
         
    def edgeFound(self, result, pointClicked):
        
        try:self.segmentFinderTool.segmentFound.disconnect() 
        except Exception: pass
        
        self.segmentFinderTool.deactivate()
        
        if self.step == 0 or self.step == 2:
            self.snappingResults.append(result)
            self.snappingPointsClicked.append(pointClicked)
            
            self.rubberBandSelectedSegment.reset(QGis.Line)
            self.rubberBandSelectedSegment.addPoint(result.beforeVertex)
            self.rubberBandSelectedSegment.addPoint(result.afterVertex, True)
            self.rubberBandSelectedSegment.show()
            
            self.step+=1 
        else:
            # step 1 or 3
            p=self._getSubPolyline(self.snappingResults[-1],result, self.snappingPointsClicked[0])
            if p:
                self.subPolylines.append(p)
                
                self.snappingResults.append(result)
                self.snappingPointsClicked.append(pointClicked)
                
                self.rubberBandSelectedSegment.reset(QGis.Line)
                self.rubberBandSelectedLine.reset(QGis.Line)
                
                if self.step==1:
                    # don't draw when step is 3
                    polyline=QgsGeometry.fromPolyline(p)
                    self.rubberBandSelectedLine.setToGeometry(polyline, self.snappingResults[0].layer)
                    self.rubberBandSelectedLine.show()
                
                self.step+=1 
            else:
                # not valid choice for second segment: not on same layer or feature or subpolyline (if multipolyline)
                self.messageBarUtils.showMessage("Centerline", 
                                                 "Invalid choice for second segment: Select a segment in the same part of the same geometry as the first", 
                                                 QgsMessageBar.WARNING, duration=5)   
            
        self.next()
        
    def lastEdgeFound(self, candidateLayers, combobox,  result, pointClicked):
        try:
            index=combobox.currentIndex()
            self.defaultIndex=index
            self.outputLayer=candidateLayers[index]
        except:
            # can happen in message with comobobox is closed by the user
            self.outputLayer=candidateLayers[self.defaultIndex]
        
        self.edgeFound(result, pointClicked)
        
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
            qDebug("New Centerline Advanced")
            
            p1=self.subPolylines[0]
            p2=self.subPolylines[1]
                        
            if self._mustReverse(p1,p2):
                # reverse the node order of any of the 2
                p1=list(reversed(p1))
                
            # both input geometries and output layer are in same CRS
            if len(p1) == len(p2):
                p=self._processSimple(p1, p2)
            else:
                # voronoi with post processing
                p=self._processVoronoiPolygons(p1, p2)
            
            if p:
                self.outputLayer.beginEditCommand("Centerline")
                
                fieldCount=self.outputLayer.dataProvider().fields().count()
                feature=QgsFeature()
                feature.initAttributes(fieldCount)
                feature.setGeometry(p)
                self.outputLayer.addFeature(feature)
                
                self.outputLayer.endEditCommand()
                self.iface.mapCanvas().refresh()
                
                self.messageBarUtils.showMessage("Centerline", "The centerline was created successfully", duration=2)
            else:
                self.messageBarUtils.showMessage("Centerline", "No centerline was created", QgsMessageBar.WARNING, duration=2)   
            
        except Exception as e:
            raise
            QgsMessageLog.logMessage(repr(e))
            self.messageBarUtils.showMessage("Centerline", "There was an error performing this command. See QGIS Message log for details", QgsMessageBar.CRITICAL, duration=5)   
            self.outputLayer.destroyEditCommand()
            self.done()
            
        self.resetCenterline()
        self.next()

    def _processSimple(self, p1, p2):
        #just iterate 
        p=[]
        for i in range(len(p1)):
            endSegment=[p1[i],p2[i]]
            # middle of each end segments
            centerlineEndPoint=QgsPoint((endSegment[0].x()+endSegment[1].x())/2,
                                         (endSegment[0].y()+endSegment[1].y())/2)
            p.append(centerlineEndPoint)
        return QgsGeometry.fromPolyline(p)

    def _processVoronoiPolygons(self, p1, p2):
        tempDir=None
        try:
            # define a polygon formed by p1 and p2: add edge at both ends to
            # close it. P1 and p2 have already been ordered to face each other
            # in the same direction
            ring=p1[0:]
            ring.extend([p1[-1],p2[-1]])
            ring.extend(p2[-1::-1])
            ring.extend([p2[0],p1[0]])
            pipePolygon=QgsGeometry.fromPolygon([ring])
            end1=QgsGeometry.fromPolyline([p1[-1],p2[-1]])
            end2=QgsGeometry.fromPolyline([p2[0],p1[0]])
            
            # create temp shp 
            tempDir = tempfile.mkdtemp()
            vl=QgsVectorLayer("LineString?crs=%s" % self.outputLayer.crs().toWkt(), "temp", "memory")
            pr = vl.dataProvider()
            vl.startEditing()
            pr.addAttributes([QgsField("id",QVariant.Int,"Integer")])
            vl.commitChanges()
            
            vl.startEditing()
            for p in [p1,p2]:
                feature=QgsFeature()
                feature.initAttributes(1)
                feature.setGeometry(QgsGeometry.fromPolyline(p))
                vl.addFeature(feature)
            vl.commitChanges()
            
            qDebug("mem " + repr(vl.featureCount()))
            
            inputShp=os.path.join(tempDir,"input.shp")
            QgsVectorFileWriter.writeAsVectorFormat(vl, inputShp , "UTF-8", vl.crs())
    
            
#             vl=QgsVectorLayer("Polygon?crs=%s" % self.outputLayer.crs().toWkt(), "temp3", "memory")
#             pr = vl.dataProvider()
#             vl.startEditing()
#             pr.addAttributes([QgsField("id",QVariant.Int,"Integer")])
#             vl.commitChanges()
#             vl.startEditing()
#             feature=QgsFeature()
#             feature.initAttributes(1)
#             feature.setGeometry(pipePolygon)
#             vl.addFeature(feature)
#             vl.commitChanges()
            # QgsMapLayerRegistry.instance().addMapLayer(vl)
            
            # processing often fails randomly
            # try multiple times
            trials=0
            success=False
            while trials < 3 and not success:
                try:
                    output=processing.runalg("qgis:densifygeometries",inputShp, 100,None)
                    output=processing.runalg("qgis:extractnodes",output["OUTPUT"],None)
                    output=processing.runalg("qgis:voronoipolygons",output["OUTPUT"],0.001,None)
                    voronoi=QgsVectorLayer(output["OUTPUT"],"voronoi","ogr")
#                     QgsMapLayerRegistry.instance().addMapLayer(voronoi, addToLegend=True)
#                     voronoi.setLayerTransparency(50)
                    
                    output=processing.runalg("qgis:extractnodes",inputShp, None)
                    originalNodes=QgsVectorLayer(output["OUTPUT"],"original","ogr")
                    
                    success=originalNodes.featureCount > 0 and  voronoi.featureCount() > 0
                except:
                    trials+=1
                    
            if not success:
                return None
            
            qDebug("after processing")
            
            # 1. create a spatial index with all the voronoi polygons
            # 2. Get the lsit of edges from the vornoi polygons that are in the pipePolygon
            voronoiEdges=[]
            voronoiEdgeInsideSet=set()
            spatialIndex=QgsSpatialIndex()
            for f in voronoi.getFeatures():
                spatialIndex.insertFeature(f)
                geometry=f.geometry()
                
                # voronoi polygons are single parts with one ring
                p=geometry.asPolygon()
                for edgeP in self._extractEdgesFromPolyline(p[0]):
                    edge=QgsGeometry.fromPolyline(edgeP)
                    if edge.within(pipePolygon):
                        key=self._keyFromEdge(edgeP)
                        if key not in voronoiEdgeInsideSet:
                            # prevent duplicates (voronoi polygons share a border)
                            voronoiEdges.append(edgeP)
                            voronoiEdgeInsideSet.add(key)
                            
            
            voronoiPolygonMajorEdges=[]
            qDebug(repr(originalNodes.featureCount()))
            for originalNode in originalNodes.getFeatures():
                geometry=originalNode.geometry()
                candidates=spatialIndex.intersects(geometry.boundingBox())
                if len(candidates)>0:
                    for candidate in candidates:
                        fCandidate=voronoi.getFeatures(QgsFeatureRequest(candidate)).next()
                        gCandidate=fCandidate.geometry()
                        if geometry.within(gCandidate):
                            p=gCandidate.asPolygon()
                            edges=self._extractEdgesFromPolyline(p[0])
                            for edge in edges:
                                key=self._keyFromEdge(edge)
                                if key not in voronoiEdgeInsideSet:
                                    # do not add the edge if already in the centerline
                                    #gEdge=QgsGeometry.fromPolyline(edge)
                                    #if gEdge.intersects(pipePolygon):
                                    voronoiPolygonMajorEdges.append(key)
                            break
            
            qDebug("after spatindex")
            
            # recursively combine voronoiedges into one big polyline
            voronoiEdges=QgsGeometry.fromMultiPolyline(voronoiEdges)
            centerlinePolyline=voronoiEdges.combine(voronoiEdges) #self.union(voronoiEdges)
            
            if centerlinePolyline.isMultipart():
                lines=centerlinePolyline.asMultiPolyline()
            else:
                lines=[centerlinePolyline.asPolyline()]
            
            
            qDebug("after merge")
            
            # key template
            kT="%3.11f"
            
            nodeToVertexIndex={}
            nodeCount={}
            for i in range(len(lines)):
                line=lines[i]
                for j in range(len(line)):
                    point=line[j]
                    key=(kT%point.x(),kT%point.y())
                    count=nodeCount.get(key,0)
                    if j <> 0 and j <>len(line)-1:
                        # each of those nodes is linked to 2 segments
                        count += 2
                    else:
                        count += 1
                    nodeCount[key]=count
                    
                    nodeToVertexIndex[key]=(i,j)
                    
#             for i in range(len(lines)):
#                 line=lines[i]
#                 for j in range(len(line)):
#                     point=line[j]
#                     key=(kT%point.x(),kT%point.y())
#                     qDebug(repr(key)+" "+repr(nodeCount[key]))
                    
            for edgeKey in voronoiPolygonMajorEdges:
                p1x,p1y,p2x,p2y=edgeKey
                for key in [(kT%p1x,kT%p1y),(kT%p2x,kT%p2y)]:
                    if key==('-76.87093621506', '42.15309787572'):
                        qDebug("found mine " + repr(nodeCount.get(key,0)))
                    count=nodeCount.get(key,0)
                    if count == 2:
                        # only counts if in the main segment (not the branches)
                        nodeCount[key]=count+1
                    
            qDebug("after indexing")
            
            # cleanup: only keep important vertices
            toKeep=set(filter(lambda x:nodeCount[x] > 2, nodeCount.keys()))
            toRemove=set(nodeToVertexIndex.keys()) - toKeep
            toRemoveIndices=map(lambda x:nodeToVertexIndex[x], toRemove)
            for lineIndex,pointIndex in sorted(toRemoveIndices, cmp=self._compareIndices,reverse=True):
                line=lines[lineIndex]
                del line[pointIndex]
                    
            self._cleanupDegenerateSegments(lines)
            
            qDebug("after cleanup")
            
            return self.union(map(lambda x:QgsGeometry.fromPolyline(x), lines))
        finally:
            if tempDir:
                pass #shutil.rmtree(tempDir, True)
            qDebug("after union")
            
    def union(self, lines):
        return reduce(lambda m,x:m.combine(x),lines[1:],lines[0])
            
    def _compareIndices(self, x, y):
        i1,j1=x
        i2,j2=y
        if i1 < i2:
            return -1
        elif i2 < i1:
            return 1
        else:
            if j1 < j2:
                return -1
            elif j2 < j1:
                return 1
            else:
                return 0
            
    def _keyFromEdge(self, edge):
        return (edge[0].x(),edge[0].y(),edge[1].x(),edge[1].y())
            
    def _cleanupDegenerateSegments(self, lines):
        linesToRemove=[]
        for i in range(len(lines)):
            line=lines[i]
            if len(line) <= 1:
                linesToRemove.append(i)
        
        for i in reversed(linesToRemove):
            del lines[i]
        
        return lines
                
    def _extractEdgesFromPolyline(self, p):
        edges=[]
        for i in range(len(p)-1):
            edgeP=p[i:i+2]
            edges.append(edgeP)
        return edges
    
    def _mustReverse(self, p1,p2):
        polyline1=QgsGeometry.fromPolyline(p1)
        polyline2=QgsGeometry.fromPolyline(p2)
        
        candidates1=(QgsGeometry.fromPolyline([p1[0],p2[0]]),
                    QgsGeometry.fromPolyline([p1[-1],p2[-1]]))
        
        return ((candidates1[0].intersects(candidates1[1]) and not candidates1[0].equals(candidates1[1])) or 
                polyline1.crosses(candidates1[0]) or polyline1.crosses(candidates1[1]) or 
                polyline2.crosses(candidates1[0]) or polyline2.crosses(candidates1[1]) )
    
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
    
    def _getSubPolyline(self, snappingResult1, snappingResult2, pointClicked1):
        """
        computes the polyline defined by the 2 segments: all the segments between those 2
        will be included in the returned polyline. If Ctrl held while selecting the 2nd segment, 
        The side of the first segment the user clicked on determines which direction to go to add those segments
        """
        if (snappingResult1.layer.id() <> snappingResult2.layer.id() or 
            snappingResult1.snappedAtGeometry <> snappingResult2.snappedAtGeometry):
            return None
        
        feature = self._getFeature(snappingResult1)
        geometry = feature.geometry()
        
        if geometry.isMultipart():
            mp=geometry.asMultipolyline()
            p, relative=vectorlayerutils.polylineWithVertexAtIndex(mp, snappingResult1.beforeVertexNr)
            _,relative2=vectorlayerutils.polylineWithVertexAtIndex(mp, snappingResult2.beforeVertexNr)
            if relative <> relative2:
                # not on the same sub polyline
                return None
        else:
            p=geometry.asPolyline()
            relative=0
        
        if self.orderSelection:    
            bv = geometry.vertexAt(snappingResult1.beforeVertexNr)
            av = geometry.vertexAt(snappingResult1.afterVertexNr)
            
            # get the direction in which to add segments
            # vertex closest to point clicked is the top vertex: direction will be from
            # the other vertex to that one
            extendUtils=ExtendUtils(self.iface)
            vertexNrDirection = extendUtils.vertexIndexToMove(bv, av, snappingResult1, 
                                                       pointClicked1, mustExtend=False)
            
            # positive if index of vertices is incremented
            direction=vertexNrDirection == snappingResult1.afterVertexNr
            
            if not direction:
                # swap
                temp=snappingResult2
                snappingResult2=snappingResult1
                snappingResult1=temp
            
            if snappingResult2.afterVertexNr <= snappingResult1.beforeVertexNr:
                # wrap around
                nodes=p[snappingResult1.beforeVertexNr-relative:]
                nodes.extend(p[0:snappingResult2.afterVertexNr-relative+1])
            else:
                nodes=p[snappingResult1.beforeVertexNr-relative:snappingResult2.afterVertexNr-relative+1]
        else:
            if snappingResult2.beforeVertexNr < snappingResult1.beforeVertexNr:
                # swap
                temp=snappingResult2
                snappingResult2=snappingResult1
                snappingResult1=temp
                direction=False
            else:
                direction=True

            nodes=p[snappingResult1.beforeVertexNr-relative:snappingResult2.afterVertexNr-relative+1]
        
        qDebug(repr(nodes))
        
        return nodes if direction else list(reversed(nodes))
        
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
        
        self.orderSelection=e.modifiers() == Qt.ControlModifier
        qDebug(repr(self.orderSelection))
        
        if self.currentMapTool:
            self.currentMapTool.canvasPressEvent(e)

    def canvasReleaseEvent(self, e):
        if self.currentMapTool:
            self.currentMapTool.canvasReleaseEvent(e)

    def canvasMoveEvent(self, e):
        if self.currentMapTool:
            self.currentMapTool.canvasMoveEvent(e)
            
    def snap(self, pos):
        (_, result) = self.snapper.snapToBackgroundLayers(pos)
        return result

def sqDistance(pt1, pt2):
    return (pt1.x() - pt2.x())**2 + (pt1.y() - pt2.y())**2