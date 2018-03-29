# -*- coding: utf-8 -*-

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *
import processing
from messagebarutils import MessageBarUtils
import vectorlayerutils
from polygonizedialog import PolygonizeDialog
import constants

import tempfile
import shutil
import os

class PolygonizeCommand(object):
         
    def __init__(self, iface):
        self.iface = iface
        self.messageBarUtils = MessageBarUtils(iface)
        
    def run(self): 
        self.layer = self.iface.legendInterface().currentLayer()
        
        if self.layer.isModified():
            self.messageBarUtils.showMessage("Polygonize", "Commit current changes in layer before running this command.", 
                                               QgsMessageBar.CRITICAL, duration=5)
            return
        
        if self.layer.featureCount() == 0:
            self.messageBarUtils.showMessage("Polygonize", "Current layer is empty!", 
                                               QgsMessageBar.WARNING, duration=5)
            return
        
        self.polygonLayers, self.nonDigitLayerIndex = self.getPolygonLayerList()
        if len(self.polygonLayers) == 0:
            self.messageBarUtils.showMessage("Polygonize", "No polygon layer in TOC.", 
                                               QgsMessageBar.WARNING, duration=5)
            return
        
        if self.layer.selectedFeatureCount() == 0:
            self.messageBarUtils.showYesCancel("Polygonize", "No feature selected in Layer %s. Proceed on full layer?" % self.layer.name(), 
                                               QgsMessageBar.WARNING, self.showDialog)
            return
        
        self.showDialog()
        
    def showDialog(self):
        dialog = PolygonizeDialog(self.polygonLayers, self.nonDigitLayerIndex)
        dialog.show()
        result = dialog.exec_()
        if result == 1:
            self.polygonize(dialog.selectedLayer, dialog.append)
        
    def getPolygonLayerList(self):        
        polygonLayers = []
        legend = self.iface.legendInterface()
        nonDigitLayerName = None
        if "_DIGIT" in self.layer.name():
            # output in the non digit polygon layer
            nonDigitLayerName = self.layer.name().replace("_DIGIT", "")
        
        nonDigitLayerIndex = None
        for layer in legend.layers():
            if layer.type() == QgsMapLayer.VectorLayer and layer.geometryType() == QGis.Polygon:
                polygonLayers.append(layer)
                if nonDigitLayerName == layer.name():
                    nonDigitLayerIndex = len(polygonLayers) - 1
                    
        return polygonLayers, nonDigitLayerIndex
    
    def polygonize(self, outputLayer, append):
        try:
            from shapely.ops import polygonize
            from shapely.geometry import Point, MultiLineString
        except ImportError:
            self.messageBarUtils.showMessage("Polygonize", "Polygonize requires the Shapely Python module. Please contact your administrator.", QgsMessageBar.CRITICAL, 5)
            return
        
        self.outputLayer = outputLayer
        self.append = append
        
        outputEditable = False
        if self.outputLayer.isEditable():
            outputEditable = True
            self.outputLayer.beginEditCommand("Polygonize")
        else:
            self.outputLayer.startEditing()    
        
        grassOutputLayer=None
        tempDir = None
        try:
            
            selected = self.layer.selectedFeatureCount() > 0
            
            tempDir = tempfile.mkdtemp()
            shpPath = os.path.join(tempDir, "temp.shp")
            QgsVectorFileWriter.writeAsVectorFormat(self.layer, shpPath, self.layer.dataProvider().encoding(), 
                                                    self.layer.crs(), onlySelected=selected)
            grassOutputLayer = self.cleanupGRASS(shpPath)
            
            
            self.iface.mainWindow().statusBar().showMessage("Cleanup duplicate and degenerate lines")
            allLinesList = self.cleanupDuplicateAndDegenerateLines(grassOutputLayer)
            
            _, progress = self.messageBarUtils.showProgress("Polygonize", "Running...", QgsMessageBar.INFO)
                
            
            self.iface.mainWindow().statusBar().showMessage("Shapely polygonize")
                
            progress.setValue(10)
            allLines = MultiLineString(allLinesList)
            allLines = allLines.union(Point(0, 0))
            progress.setValue(25)
            polygons = list(polygonize([allLines]))
            progress.setValue(35)
            
            outFeat = QgsFeature()
            
            outputFields = self.outputLayer.dataProvider().fields()
            
            
            self.iface.mainWindow().statusBar().showMessage("Freeze canvas before update")
            
            self.iface.mapCanvas().freeze(True)
            
            if not append:
                # delete all features in outputlayer
                for feature in self.outputLayer.getFeatures():
                    self.outputLayer.deleteFeature(feature.id())
            
            progress.setValue(50)
            
            
            self.iface.mainWindow().statusBar().showMessage("add to output")
            
            current = 0
            if len(polygons) > 0:
                total = 50.0 / float(len(polygons))
                for polygon in polygons:
                    geom = QgsGeometry.fromWkt(polygon.wkt)
                    outFeat.setGeometry(geom)
                    outFeat.initAttributes(outputFields.count())
                    self.outputLayer.addFeature(outFeat)
                    current += 1
                    progress.setValue(50 + int(current * total))
                
                self.messageBarUtils.showMessage("Polygonize", "Success: %d polygons created in %s" %(current, self.outputLayer.name()), QgsMessageBar.INFO, 2)
            else:
                self.messageBarUtils.showMessage("Polygonize", "No polygon was created", QgsMessageBar.WARNING, 2)
                
        except Exception as e:
            QgsMessageLog.logMessage(repr(e))
            self.messageBarUtils.removeAllMessages()
            self.messageBarUtils.showMessage("Polygonize", "There was an error performing this command. See QGIS Message log for details.", QgsMessageBar.CRITICAL, duration=5)
            
            if outputEditable:
                self.outputLayer.destroyEditCommand()
            else:
                self.outputLayer.rollBack()
            return
        finally:
            if tempDir:
                shutil.rmtree(tempDir, True)
            if grassOutputLayer:
                del grassOutputLayer
            self.iface.mapCanvas().freeze(False)
            self.iface.mapCanvas().refresh()
        
        if outputEditable:
            self.outputLayer.endEditCommand()
        else:
            self.outputLayer.commitChanges()
            
    def cleanupGRASS(self, layer):
        
        layer = QgsVectorLayer(layer, "Temp", "ogr")
    
        self.iface.mainWindow().statusBar().showMessage("GRASS cleanup: Layer Intersection")
    
        layer.startEditing()
        vectorlayerutils.layerIntersection(layer)
        layer.commitChanges() 
        
        self.iface.mainWindow().statusBar().showMessage("GRASS cleanup: v.clean Snap")
        
        # v.clean Snap
        # will make sure the nodes snapped to a segment are taken into account during v.clean break
        # tolerance in m => 1mm
        output = processing.runalg("grass:v.clean",layer,1,constants.TOLERANCE_DEGREE,None,-1,0.0001,None,None)
        outputLayer = output['output']
        del layer
        
        
        self.iface.mainWindow().statusBar().showMessage("GRASS cleanup: v.clean rmdupl")
        
        # v.clean rmdupl
        output = processing.runalg("grass:v.clean",outputLayer,6,0,None,-1,0.0001,None,None)
        if output and os.path.exists(output['output']):
            outputLayer = output['output']
            
        
        self.iface.mainWindow().statusBar().showMessage("GRASS cleanup: v.clean rmline")
        
        # v.clean rmline
        output = processing.runalg("grass:v.clean",outputLayer,11,0,None,-1,0.0001,None,None)
        if output and os.path.exists(output['output']):
            outputLayer = output['output']
            
        
        self.iface.mainWindow().statusBar().showMessage("GRASS cleanup: Open layer")
        
        outputLayer = QgsVectorLayer(outputLayer, "Repr", "ogr")
        
        return outputLayer   
        
    def cleanupDuplicateAndDegenerateLines(self, layer):
        allLinesList = []
        wkts = set()
        features = layer.getFeatures()
        for inFeat in features:
            inGeom = inFeat.geometry()
            if inGeom.isMultipart():
                for polyline in inGeom.asMultiPolyline():
                    if self.checkPolyline(self.cutAtVertices(polyline), wkts):
                        allLinesList.extend(polyline)
                    else:
                        QgsMessageLog.logMessage("Bad polyline: " + str(inFeat.id()))
            else:
                polyline = inGeom.asPolyline()
                if self.checkPolyline(polyline, wkts):
                    allLinesList.extend(self.cutAtVertices(polyline))
                else:
                    QgsMessageLog.logMessage("Bad polyline: " + str(inFeat.id()))
            
        return allLinesList
        
    def cutAtVertices(self,polyline):
        cut=[]
        for i in range(1,len(polyline)):
            cut.append(polyline[i-1:i+1])
        return cut
        
    def checkPolyline(self, polyline, wkts):
        # check degenerate
        if self.checkDegeneratePolyline(polyline):
            wkt = QgsGeometry.fromPolyline(polyline).exportToWkt()
            # check duplicate
            if wkt in wkts:
                return False
            else:
                wkts.add(wkt)
                return True
        else:
            return False
            
    def checkDegeneratePolyline(self, polyline):
        return len(polyline) >= 2
