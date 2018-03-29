# -*- coding: utf-8 -*-

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *
import processing
import os
import tempfile
import shutil

from messagebarutils import MessageBarUtils
import vectorlayerutils
import constants

class IntersectCommand(object):
    
    def __init__(self, iface):
        self.iface = iface
        self.messageBarUtils = MessageBarUtils(iface)
        
    def run(self):
        self.layer = self.iface.legendInterface().currentLayer()
        
        if self.layer.isModified():
            self.messageBarUtils.showMessage("Intersect", "Commit current changes in layer before running this command.", 
                                               QgsMessageBar.CRITICAL, duration=5)
            return
        
        if self.layer.selectedFeatureCount() == 0:
            self.messageBarUtils.showYesCancel("Intersect", "No feature selected in Layer %s. Proceed on full layer?" % self.layer.name(), 
                                               QgsMessageBar.WARNING, self.intersect)
            return
        
        # run directly without asking anything
        self.intersect()
    
    def intersect(self):
        self.layer.beginEditCommand("Intersect")
        
        tempDir = None
        try:
            self.iface.mapCanvas().freeze(True)
            
            if self.layer.selectedFeatureCount() > 0:
                selected=True
                concernedFids = self.layer.selectedFeaturesIds()
            else:
                concernedFids = self.layer.allFeatureIds()
                selected=False
                
            
            tempDir = tempfile.mkdtemp()
            shpPath = os.path.join(tempDir, "temp.shp")
            # not really necessary if no selection....
            QgsVectorFileWriter.writeAsVectorFormat(self.layer, shpPath, self.layer.dataProvider().encoding(), 
                                                    self.layer.crs(), onlySelected=selected)
            
            # here run own implementation of intersection instead of v:clean break => v.clean break applies a threshold
            # that merges vertices closer than 10^-4 to each other (no matter the unit), which is a problem for 
            # goographic coordinates (10^-4 deg ~ 100m at equator). Possible to reproject instead but intersections not exactly where
            # they would have been (line in WGS84 is not a line in Mercator but reproject only reprojects the endpoint) 
            # and someone would have complained (even though at the scale we work at; it would have been a distortion < 1mmm)
            # To consider if the method below is too slow...
            layer = QgsVectorLayer(shpPath, "Temp", "ogr")
            
            self.iface.mainWindow().statusBar().showMessage("Layer Intersection")
    
            layer.startEditing()
            vectorlayerutils.layerIntersection(layer)
            layer.commitChanges() 
            
            self.iface.mainWindow().statusBar().showMessage("v.clean snap")
            
            # v.clean Snap
            # will make sure the nodes snapped to a segment are taken into account
            # tolerance set to close to floating precision
            output = processing.runalg("grass:v.clean",layer,1,constants.TOLERANCE_DEGREE,None,-1,0.0001,None,None)
            outputLayer = output['output']
            
            # here selection has been lost but not a problem in practice
            
            
            self.iface.mainWindow().statusBar().showMessage("v.clean rmdupl")
            
            # v.clean rmdupl
            output = processing.runalg("grass:v.clean",outputLayer,6,0,None,-1,0.0001,None,None)
            outputLayer = output['output']
            
            
            self.iface.mainWindow().statusBar().showMessage("v.clean rmline")
            
            # v.clean rmline
            output = processing.runalg("grass:v.clean",outputLayer,11,0,None,-1,0.0001,None,None)
            outputLayer = output['output']
            
            outputLayer = QgsVectorLayer(outputLayer, "Repr", "ogr")
                
            self.iface.mainWindow().statusBar().showMessage("output")
                
            # copy output features
            count = outputLayer.featureCount()
            qDebug("Count %d" % count)
            if count == 0:
                self.messageBarUtils.showMessage("Intersect", "No feature output.", QgsMessageBar.WARNING, duration=5)
            else:
                # delete original selected features
                for featureId in concernedFids:
                    self.layer.deleteFeature(featureId)
                    
                for feature in outputLayer.getFeatures():
                    geom = feature.geometry()
                    feature.setGeometry(geom)
                    self.layer.addFeature(feature)
                    if selected:
                        self.layer.select(feature.id())
                    
            del outputLayer
            
        except Exception as e:
            QgsMessageLog.logMessage(repr(e))
            self.messageBarUtils.removeAllMessages()
            self.messageBarUtils.showMessage("Intersect", "There was an error performing this command. See QGIS Message log for details.", 
                                             QgsMessageBar.CRITICAL, duration=5)
            
            self.layer.destroyEditCommand()
       
            return
        finally:
            if tempDir:
                shutil.rmtree(tempDir, True)
            self.iface.mapCanvas().freeze(False)
            self.iface.mapCanvas().refresh()
            
        self.messageBarUtils.showMessage("Intersect", "Success", duration=5)
        
        self.layer.endEditCommand()
            
