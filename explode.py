# -*- coding: utf-8 -*-

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *

from messagebarutils import MessageBarUtils
import vectorlayerutils

class ExplodeCommand(object):
    
    def __init__(self, iface):
        self.iface = iface
        self.messageBarUtils = MessageBarUtils(iface)
        
    def run(self):
        self.vlayer = self.iface.legendInterface().currentLayer()
        
        if self.vlayer.selectedFeatureCount() == 0:
            self.messageBarUtils.showYesCancel("Explode", "No feature selected in Layer %s. Proceed on full layer?" % self.vlayer.name(), 
                                               QgsMessageBar.WARNING, self.explode)
            return
        
        # run directly without asking anything
        self.explode()
    
    def explode(self):
        self.vlayer.beginEditCommand("Explode")
            
        _, progress = self.messageBarUtils.showProgress("Explode", "Running...", QgsMessageBar.INFO)
        
        try:
            self.iface.mapCanvas().freeze(True)
    
            outFeat = QgsFeature()
            inGeom = QgsGeometry()
    
            current = 0
            features = vectorlayerutils.features(self.vlayer)
            total = 100.0 / float(len(features))
            for f in features:
                inGeom = f.geometry()
                attrs = f.attributes()
    
                geometries = self.extractAsSingle(inGeom)
                outFeat.setAttributes(attrs)
    
                for g in geometries:
                    outFeat.setGeometry(g)
                    self.vlayer.addFeature(outFeat)
                    
                # delete original feature
                self.vlayer.deleteFeature(f.id())
    
                current += 1
                progress.setValue(int(current * total))

        except Exception as e:
            QgsMessageLog.logMessage(repr(e))
            self.messageBarUtils.removeAllMessages()
            self.messageBarUtils.showMessage("Explode", "There was an error performing this command. See QGIS Message log for details.", 
                                             QgsMessageBar.CRITICAL, duration=5)
            if self.vlayer.isEditable():
                self.vlayer.destroyEditCommand()
            
            return
        finally:
            self.iface.mapCanvas().freeze(False)
            self.iface.mapCanvas().refresh()
        
        # if here: Success!
        self.messageBarUtils.removeAllMessages()
        self.messageBarUtils.showMessage("Explode", "Success", QgsMessageBar.INFO, 5)
        
        self.vlayer.endEditCommand()

    def extractAsSingle(self, geom):
        multiGeom = QgsGeometry()
        geometries = []
        if geom.type() == QGis.Point:
            if geom.isMultipart():
                multiGeom = geom.asMultiPoint()
                for i in multiGeom:
                    geometries.append(QgsGeometry().fromPoint(i))
            else:
                geometries.append(geom)
        elif geom.type() == QGis.Line:
            if geom.isMultipart():
                multiGeom = geom.asMultiPolyline()
                for i in multiGeom:
                    geometries.append(QgsGeometry().fromPolyline(i))
            else:
                geometries.append(geom)
        elif geom.type() == QGis.Polygon:
            if geom.isMultipart():
                multiGeom = geom.asMultiPolygon()
                for i in multiGeom:
                    geometries.append(QgsGeometry().fromPolygon(i))
            else:
                geometries.append(geom)
        return geometries
