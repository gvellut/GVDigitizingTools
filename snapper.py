# -*- coding: utf-8 -*-

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *

import vectorlayerutils
import sys

class Snapper(object):
    
    def __init__(self, canvas, layers, snap_to,snappingTol=-1):
        self.canvas=canvas
        self.snapper=self._prepareSnapper(layers, snap_to, snappingTol)
        
    def snap(self, startingPoint):
        _, results = self.snapper.snapPoint(startingPoint)
                         
        # so if we have found a vertex
        if results <> []:
            if len(results)>1:
                # some processing here because of some precision issue in snapping with with geographic CRS
                globalMinDist=sys.float_info.max
                globalMinDistVertexNr=None
                globalMinDistFeatureId=None
                globalMinDistPoint=None
                globalMinDistLayer=None
                featureSeen=set()
                mapStartingPoint=self.canvas.mapSettings().mapToPixel().toMapPoint(startingPoint.x(),startingPoint.y())
                for index in range(len(results)):
                    result=results[index]
                    
                    layer=result.layer
                    layerCoordPoint=self.canvas.mapSettings().mapToLayerCoordinates(layer, mapStartingPoint)
                    feature=self._getFeature(result)
                    
                    key=(layer,feature.id())
                    if key in featureSeen:
                        continue
                    
                    featureSeen.add(key)
                    geometry=feature.geometry()
                    if geometry.isMultipart():
                        offset=0
                        for p in geometry.asMultiPolyline():
                            minDist,minDistVertexNr,minDistPoint=vectorlayerutils.closestSegmentWithContext(layerCoordPoint,p)
                            if minDist < globalMinDist:
                                globalMinDist=minDist
                                globalMinDistVertexNr=offset+minDistVertexNr
                                globalMinDistFeatureId=feature.id()
                                globalMinDistPoint=minDistPoint
                                globalMinDistLayer=layer
                            offset+=len(p)
                    else:
                        minDist,minDistVertexNr,minDistPoint=vectorlayerutils.closestSegmentWithContext(layerCoordPoint, geometry.asPolyline())
                        qDebug(repr(minDist)+" "+repr(minDistVertexNr)+" "+repr(minDistPoint))
                        if minDist < globalMinDist:
                            globalMinDist=minDist
                            globalMinDistVertexNr=minDistVertexNr
                            globalMinDistFeatureId=feature.id()
                            globalMinDistPoint=minDistPoint
                            globalMinDistLayer=layer
                            
                feature=globalMinDistLayer.getFeatures(QgsFeatureRequest(globalMinDistFeatureId)).next()
                geometry=feature.geometry()
                
                snappingResult=QgsSnappingResult()
                snappingResult.afterVertexNr=globalMinDistVertexNr
                snappingResult.beforeVertexNr=globalMinDistVertexNr-1
                snappingResult.afterVertex=self.canvas.mapSettings().layerToMapCoordinates(globalMinDistLayer,
                                                                                           geometry.vertexAt(snappingResult.afterVertexNr))
                snappingResult.beforeVertex=self.canvas.mapSettings().layerToMapCoordinates(globalMinDistLayer,
                                                                                            geometry.vertexAt(snappingResult.beforeVertexNr))
                snappingResult.layer=globalMinDistLayer
                snappingResult.snappedAtGeometry=globalMinDistFeatureId
                snappingResult.snappedVertex=self.canvas.mapSettings().layerToMapCoordinates(layer,globalMinDistPoint)
                snappingResult.snappedVertexNr=-1
            else:
                snappingResult=results[0]
            return snappingResult
        else:
            return None
    
    def _prepareSnapper(self, layers, snap_to, snappingTol=-1):
        if not layers or len(layers)==0:
            layers=[self.canvas.currentLayer()]
            
        snapLayers=[]
        for layer in layers:
            snapLayer=QgsSnapper.SnapLayer()
            snapLayer.mLayer = layer
            snapLayer.mSnapTo = snap_to
            snapLayer.mUnitType = QgsTolerance.MapUnits
            if snappingTol < 0 :
                snapLayer.mTolerance = QgsTolerance.vertexSearchRadius( layer, self.canvas.mapSettings() )
            else:
                snapLayer.mTolerance = snappingTol
            snapLayers.append(snapLayer)
            
        snapper=QgsSnapper(self.canvas.mapRenderer())
        snapper.setSnapMode( QgsSnapper.SnapWithResultsWithinTolerances )
        snapper.setSnapLayers(snapLayers)  
        return snapper
          
    
    def _getFeature(self, snappingResult):
        fid = snappingResult.snappedAtGeometry
        feature = QgsFeature()
        fiter = snappingResult.layer.getFeatures(QgsFeatureRequest(fid))
        if fiter.nextFeature(feature):
            return feature
        return None 
    
    