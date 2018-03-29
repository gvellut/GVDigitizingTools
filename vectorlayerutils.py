# -*- coding: utf-8 -*-

# Import the PyQt and QGIS libraries
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *
import processing
import constants
import sys

def features(layer, useOnlySelected = True):
    """This returns an iterator over features in a vector layer,
    considering the selection that might exist in the layer (if none exists,
    the whole layer is returned)
    """
    class Features:

        def __init__(self, layer):
            self.layer = layer
            self.selection = False
            self.iter = layer.getFeatures()
            if useOnlySelected:
                if layer.selectedFeatureCount() > 0:
                    self.selection = True
                    request=QgsFeatureRequest()
                    request.setFilterFids(layer.selectedFeaturesIds())
                    # TODO replace by layer.selectedFeaturesIterator() in 2.6
                    self.iter = layer.getFeatures(request)

        def __iter__(self):
            return self.iter

        def __len__(self):
            if self.selection:
                return int(self.layer.selectedFeatureCount())
            else:
                return int(self.layer.featureCount())

    return Features(layer)


def reprojectToTempLayer(layer, destCrs):
    shpPath,_ = layer.dataProvider().dataSourceUri().split("|")
    return reprojectSHPToTempLayer(shpPath, destCrs)

def reprojectSHPToTempLayer(shpPath, destCrs):
    output = processing.runalg("qgis:reprojectlayer", shpPath,"EPSG:%d" % destCrs.srsid(), None)
    return output["OUTPUT"]

def memoryLayerType(wkbType):
    # remve "WKB" prefix
    return QGis.featureType(wkbType)[3:]
    
def createMemoryLayer(name, model, crs=None):
    if not crs:
        crs = model.crs() 
    vl = QgsVectorLayer(memoryLayerType(model.wkbType()) + "?crs=%s" % crs.toWkt(), name, "memory")
    pr = vl.dataProvider()
    vl.startEditing()
    pr.addAttributes(model.dataProvider().fields().toList())
    vl.commitChanges()
    return vl

def copySelectionToMemoryLayer(name, layer):
    """
    Creates a new memory layer that takes account the selection
    """
    memoryLayer = createMemoryLayer(name, layer)
    memoryLayer.startEditing()
    for feature in features(layer):
        memoryLayer.addFeature(feature, False)
    memoryLayer.commitChanges()
    return memoryLayer

def segmentIntersectionPoint(geometry1, geometry2):
    intersectionPoint = geometry1.intersection(geometry2)
    if not intersectionPoint or intersectionPoint.type() != QGis.Point:
        return None
    if intersectionPoint.isMultipart():
        # list of points
        return intersectionPoint.asMultiPoint()
    else:
        return [intersectionPoint.asPoint()]

def layerIntersection(layer):
    """
    Layer intersection
    Takes selection into account (if present)
    """
    index = QgsSpatialIndex()
    for f in features(layer):
        index.insertFeature(f)
        
    fReq = QgsFeatureRequest()
    for feature in features(layer):
        geometry = feature.geometry()
        currentFid = feature.id()
        fids = index.intersects(geometry.boundingBox())
        
        fReq.setFilterFids(fids)
        for featureTest in layer.getFeatures(fReq):
            if featureTest.id() == currentFid:
                # ignore self intersections
                continue
            
            geometryTest = featureTest.geometry()
            intersections = segmentIntersectionPoint(geometry, geometryTest)
            if intersections:
                for intersection in intersections:
                    if geometry.isMultipart():
                        # OK since there is an intersection => will be not fall on the gaps
                        polyline=flattenMultiPolyline(geometry.asMultiPolyline())
                    else:
                        polyline=geometry.asPolyline()
                        
                    _, afterVertexNr,_ = closestSegmentWithContext(intersection, polyline)
                    afterVertex=geometry.vertexAt(afterVertexNr)
                    if intersection.x() <> afterVertex.x() or intersection.y() <> afterVertex.y():
                        geometry.insertVertex(intersection.x(), intersection.y(), afterVertexNr)
            
        layer.changeGeometry(currentFid, geometry)

def closestSegmentWithContext(point, polyline, tolerance=constants.TOLERANCE_DEGREE):
    """
    geometry.closestSegmentWithContext does not support the epsilon parameter like in C++ (according to
    the documentation...) so reimplement
    """
    epsilon=tolerance**2
    minDist=sys.float_info.max
    minVertexNr=-1
    minDistPoint=None
    
    for i in range(1,len(polyline)):
        p=polyline[i]
        pm1=polyline[i-1]
        dist,distPoint=point.sqrDistToSegment(p.x(),p.y(),pm1.x(),pm1.y(),epsilon)
        if dist < minDist:
            minDist = dist
            minVertexNr=i
            minDistPoint=distPoint

    return minDist, minVertexNr, minDistPoint

def flattenMultiPolyline(multipolyline):
    output = []
    for polyline in multipolyline:
        output.extend(polyline)
    return output

def polylineWithVertexAtIndex(mp, index):
    vertexCount=0
    for index in range(len(mp)):
        p=mp[index]
        if vertexCount+len(p) > index:
            return p,vertexCount
        else:
            vertexCount+=len(p)
        
