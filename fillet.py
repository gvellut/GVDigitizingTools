# -*- coding: utf-8 -*-

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *
from extendutils import ExtendUtils
from messagebarutils import MessageBarUtils
from segmentfindertool import SegmentFinderTool
from arcutils import CircularArc
import constants
import vectorlayerutils

import math

class FilletDigitizingMode(QgsMapToolEmitPoint):
    
    MESSAGE_HEADER = "Fillet"
    DEFAULT_FILLET_RADIUS = 0
    
    def __init__(self, iface):
        self.iface = iface
        QgsMapToolEmitPoint.__init__(self, self.iface.mapCanvas())
        
        self.messageBarUtils = MessageBarUtils(iface)
        self.segmentFinderTool = SegmentFinderTool(self.iface.mapCanvas())
        self.rubberBandSegment1 = QgsRubberBand(self.iface.mapCanvas())
        self.rubberBandSegment1.setColor(QColor(255, 0, 0))
        self.rubberBandSegment1.setWidth(2)
        
        self.layer = None
        self.reset()
    
    def setLayer(self, layer):
        self.layer = layer
        
    def reset(self, clearMessages = True):
        self.step = 0
        
        self.segment1 = None
        self.segment2 = None
        
        self.rubberBandSegment1.reset(QGis.Line)
        
        try:self.segmentFinderTool.segmentFound.disconnect()
        except Exception: pass
        
        if clearMessages:
            self.messageBarUtils.removeAllMessages()
            
    def resetFillet(self):
        self.reset(False)
        
    def deactivate(self):
        self.reset()
        QgsMapToolEmitPoint.deactivate(self)
        
    def next(self):
        if self.step == 0:
            self.messageBarUtils.showButton(FilletDigitizingMode.MESSAGE_HEADER, "Select first segment", "Done", buttonCallback=self.done)
            self.currentMapTool = self.segmentFinderTool
            self.segmentFinderTool.segmentFound.connect(self.segment1Found)
            
        elif self.step == 1:
            
            filletRadius,found = QgsProject.instance().readEntry(constants.SETTINGS_KEY, 
                    constants.SETTINGS_FILLET_RADIUS, None)
            
            if not found:
                filletRadius = str(FilletDigitizingMode.DEFAULT_FILLET_RADIUS)
            
            _, lineEdit = self.messageBarUtils.showLineEdit(FilletDigitizingMode.MESSAGE_HEADER, "Select second segment and set radius:", filletRadius)
            self.lineEditFilletRadius = lineEdit
            
            self.currentMapTool = self.segmentFinderTool
            self.segmentFinderTool.segmentFound.connect(self.segment2Found)
            
        elif self.step == 2:
            self.filletRadius = self.lineEditFilletRadius.text()
            
            self.doFillet()
            
    def segment1Found(self, result, pointClicked):
        self.segment1 = result
        self.segmentFinderTool.segmentFound.disconnect(self.segment1Found)
        self.segmentFinderTool.deactivate()
        
        self.rubberBandSegment1.reset(QGis.Line)
        self.rubberBandSegment1.addPoint(result.beforeVertex)
        self.rubberBandSegment1.addPoint(result.afterVertex, True)
        self.rubberBandSegment1.show()
        
        self.step = 1
        self.next()
    
    def segment2Found(self, result, pointClicked):
        self.segment2 = result
        self.segmentFinderTool.segmentFound.disconnect(self.segment2Found)
        self.segmentFinderTool.deactivate()
        
        self.step = 2
        self.next()
         
    def doFillet(self):
        self.messageBarUtils.showMessage(FilletDigitizingMode.MESSAGE_HEADER, "Running...", QgsMessageBar.INFO, duration=0)
        
        try:
            
            crsDest = self.layer.crs()
            canvas = self.iface.mapCanvas()
            mapRenderer = canvas.mapSettings()
            crsSrc = mapRenderer.destinationCrs()
            crsTransform = QgsCoordinateTransform(crsSrc, crsDest)
            
            self.layer.beginEditCommand(FilletDigitizingMode.MESSAGE_HEADER)
            
            try:
                filletRadius = float(self.filletRadius)
                # save for next time
                QgsProject.instance().writeEntry(constants.SETTINGS_KEY, 
                    constants.SETTINGS_FILLET_RADIUS, filletRadius)
            except ValueError:
                filletRadius = FilletDigitizingMode.DEFAULT_FILLET_RADIUS
            
            # do initial computations in map canvas coordinates
            # check intersection
            
            extendUtils = ExtendUtils(self.iface)
            ip = extendUtils.intersectionPoint(self.segment1.beforeVertex, self.segment1.afterVertex, self.segment2.beforeVertex, self.segment2.afterVertex)
            
            if ip == None:
                self.messageBarUtils.showMessage(FilletDigitizingMode.MESSAGE_HEADER, "The 2 segments do not intersect. Nothing was done.", 
                                                 QgsMessageBar.WARNING, duration=5)
                
                self.layer.destroyEditCommand()
                return

            
            if filletRadius == 0:
                # reproject to layer coordinates
                ip = crsTransform.transform(ip)

                # just extend the 2 lines
                ok1 = self.extend(ip, self.segment1, extendUtils)
                ok2 = self.extend(ip, self.segment2, extendUtils)
                
                if ok1 and ok2:   
                    self.iface.mapCanvas().refresh()
                    self.messageBarUtils.showMessage(FilletDigitizingMode.MESSAGE_HEADER, "Success", QgsMessageBar.INFO, 5)
                    self.layer.endEditCommand()
                else:
                    self.messageBarUtils.showMessage(FilletDigitizingMode.MESSAGE_HEADER, "Cannot fillet segments: Amibiguous extension", QgsMessageBar.WARNING, 5)
                    self.layer.destroyEditCommand()
                    
            else:
                
                (pa, p1, p2, revert1, revert2) = self.computeArcParameters(ip, self.segment1, self.segment2, filletRadius, extendUtils)
                
                if pa == None:
                    # radius is too big
                    self.messageBarUtils.showMessage(FilletDigitizingMode.MESSAGE_HEADER, "A fillet cannot be created with those arcs.", 
                                                     QgsMessageBar.WARNING, duration=5)
                    return
                
                settings = QSettings()
                method = settings.value(constants.ARC_METHOD,  "")
                if method == constants.ARC_METHOD_NUMBEROFPOINTS:
                    value = settings.value(constants.ARC_NUMBEROFPOINTS, 0, type=int)
                else:
                    value = settings.value(constants.ARC_ANGLE, 0, type=float)
                
                # g is still in CRS of map
                g = CircularArc.getInterpolatedArc(p1,  pa,  p2,  method,  value)
                arcVertices = g.asPolyline()
                
                if len(arcVertices) >= 2:
                
                    projArcVertices = []
                    for vertex in arcVertices:
                        projArcVertices.append(crsTransform.transform(vertex))
                    
                    outFeat = QgsFeature()
                
                    fields = self.layer.dataProvider().fields()
                    outFeat.setAttributes([None] * fields.count())
                    outFeat.setGeometry(QgsGeometry.fromPolyline(projArcVertices))
                    self.layer.addFeature(outFeat)
                    
                    # trim segments
                    p1 = crsTransform.transform(p1)
                    feature1 = self.getFeature(self.segment1)
                    geom1 = feature1.geometry()
                    geom1.insertVertex(p1.x(), p1.y(), self.segment1.afterVertexNr)
                    if revert1:
                        geom1.deleteVertex(self.segment1.afterVertexNr + 1) # insertion above => +1
                    else:
                        geom1.deleteVertex(self.segment1.beforeVertexNr)
                    self.layer.changeGeometry(feature1.id(), geom1)
                        
                    p2 = crsTransform.transform(p2)
                    feature2 = self.getFeature(self.segment2)
                    geom2 = feature2.geometry()
                    geom2.insertVertex(p2.x(), p2.y(), self.segment2.afterVertexNr)
                    if revert2:
                        geom2.deleteVertex(self.segment2.afterVertexNr + 1) # insertion above => +1
                    else:
                        geom2.deleteVertex(self.segment2.beforeVertexNr)
                    self.layer.changeGeometry(feature2.id(), geom2)
                    
                    self.iface.mapCanvas().refresh()
                    self.messageBarUtils.showMessage(FilletDigitizingMode.MESSAGE_HEADER, "Success", QgsMessageBar.INFO, 5)
    
                    self.layer.endEditCommand()
                    
                else:
                    self.messageBarUtils.showMessage(FilletDigitizingMode.MESSAGE_HEADER, "No arc was created", QgsMessageBar.WARNING, duration=5)
                    self.layer.destroyEditCommand()
              
        except Exception as e:
            QgsMessageLog.logMessage(repr(e))
            self.messageBarUtils.removeAllMessages()
            self.messageBarUtils.showMessage(FilletDigitizingMode.MESSAGE_HEADER, 
                                             "There was an error performing this command. See QGIS Message log for details.", QgsMessageBar.CRITICAL,
                                             duration=5)
            self.layer.destroyEditCommand()
            
            return
        finally: 
            # select another fillet
            self.resetFillet()
            self.next()
            
        
    def extend(self, ip, snapSegment, extendUtils):
        featureExtend = self.getFeature(snapSegment)
        geometryExtend = featureExtend.geometry()
        bvExtend = geometryExtend.vertexAt(snapSegment.beforeVertexNr)
        avExtend = geometryExtend.vertexAt(snapSegment.afterVertexNr)

        number = extendUtils.vertexIndexToMove(bvExtend, avExtend, snapSegment, ip)
        if number == None:
            # not an extend
            return False
        else:
            fid = featureExtend.id()
            geometryExtend.moveVertex(ip.x(), ip.y(), number)
            self.layer.changeGeometry(fid, geometryExtend)
            return True
        
    def computeArcParameters(self, ip, snapSegment1, snapSegment2, filletRadius, extendUtils):

        bvExtend1 = snapSegment1.beforeVertex
        avExtend1 = snapSegment1.afterVertex
        # TODO => mustExtend =True and check the 2 segment have the same endpoint at ip (with some tolerance)
        iVToMove1 = extendUtils.vertexIndexToMove(bvExtend1, avExtend1, snapSegment1, ip, mustExtend=False)
        
        bvExtend2 = snapSegment2.beforeVertex
        avExtend2 = snapSegment2.afterVertex
        iVToMove2 = extendUtils.vertexIndexToMove(bvExtend2, avExtend2, snapSegment2, ip, mustExtend=False)
        
        qDebug(repr(iVToMove1) + " " + repr(iVToMove2))
        
        if iVToMove1 == None or iVToMove2 == None:
            return (None, None, None, None, None)
        
        segment1 = [bvExtend1, avExtend1]
        segment2 = [bvExtend2, avExtend2]
            
        # determine intersection point (ip) and revert if needed
        revert1 = False
        revert2 = False
        if  iVToMove1 == snapSegment1.beforeVertexNr:
            segment1[0] = ip
        else:
            revert1 = True
            segment1[1] = segment1[0]
            segment1[0] = ip
            
        if iVToMove2 == snapSegment2.beforeVertexNr:
            segment2[0] = ip
        else:
            revert2 = True
            segment2[1] = segment2[0]
            segment2[0] = ip
            
        lengthSegment1 = self.length(segment1)
        normedSegment1 = self.norm(segment1, lengthSegment1)
        lengthSegment2 = self.length(segment2)
        normedSegment2 = self.norm(segment2, lengthSegment2)
        
        midp1 = self.pointAtDist(normedSegment1, filletRadius)
        midp2 = self.pointAtDist(normedSegment2, filletRadius)
        
        # get point on bisector
        midp = QgsPoint((midp1.x() + midp2.x()) / 2.0,
                        (midp1.y() + midp2.y()) / 2.0)
        # get angles along lines from intersection
        ang1 = self.angleFromX(ip, midp1)
        ang2 = self.angleFromX(ip, midp2)
        
        # get bisector angle
        ang = self.angleFromX(ip, midp)
        
        # get a half of angle between segments
        bis = abs(ang2 - ang1) / 2.0
        # calculate hypotenuse (fillet draws slice of circle tangent to segments)
        hyp = filletRadius / math.sin(bis)
        
        # calculate another leg of a triangle 
        cat = math.sqrt(hyp** 2 - filletRadius**2)
        
        if cat > self.length(segment1) or cat > self.length(segment2):
            # radius is too big => nothing done
            return (None, None, None, None, None)
        
        # calculate point on arc
        pa = self.polarPoint(ip, ang, hyp - filletRadius)
        # calculate start point of arc
        p1 = self.polarPoint(ip, ang1, cat)
        # calculate end point of arc
        p2 = self.polarPoint(ip, ang2, cat)
        
        return (pa, p1, p2, revert1, revert2)
             
    def length(self, segment):
        return math.sqrt((segment[0].x() - segment[1].x())**2 + (segment[0].y() - segment[1].y())**2)
    
    def norm(self, segment, length):
        return [segment[0], QgsPoint(segment[0].x() + (segment[1].x() - segment[0].x())/length,segment[0].y() + (segment[1].y() - segment[0].y())/length)]
    
    def pointAtDist(self, normedSegment, dist):
        return QgsPoint(normedSegment[0].x() + dist * (normedSegment[1].x() - normedSegment[0].x()),
                        normedSegment[0].y() + dist * (normedSegment[1].y() - normedSegment[0].y()))
    
    def polarPoint(self, basepoint, angle, distance):
        return QgsPoint(basepoint.x() + (distance * math.cos(angle)),
                        basepoint.y() + (distance * math.sin(angle)))
                        
    def angleFromX(self, pt1, pt2):
        dx = pt2.x() - pt1.x()
        dy = pt2.y() - pt1.y()
        ang = math.atan2(dy, dx )
        if ang < 0.0:
            return ang + 2.0 * math.pi
        else:
            return ang
        
    def getFeature(self, snappingResult):
        fid = snappingResult.snappedAtGeometry
        feature = QgsFeature()
        fiter = self.layer.getFeatures(QgsFeatureRequest(fid))
        if fiter.nextFeature(feature):
            return feature
        return None
    
    def done(self):
        self.reset()
        self.iface.mapCanvas().unsetMapTool(self)
    
    def enter(self):
        #ignore
        pass
    
    def canvasPressEvent(self, e):
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