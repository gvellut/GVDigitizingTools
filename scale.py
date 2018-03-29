# -*- coding: utf-8 -*-
# Import the PyQt and QGIS libraries
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *
from messagebarutils import MessageBarUtils
import constants
import vectorlayerutils

class ScaleDigitizingMode(QgsMapToolEmitPoint):
    
    MESSAGE_HEADER = "Scale"
    DEFAULT_SCALE_FACTOR = 2.0
    
    def __init__(self, iface, digitizingTools):
        self.iface = iface
        self.digitizingTools = digitizingTools
        QgsMapToolEmitPoint.__init__(self, self.iface.mapCanvas())
        
        self.messageBarUtils = MessageBarUtils(iface)
        
        self.rubberBandSnap = QgsRubberBand(self.iface.mapCanvas())
        self.rubberBandSnap.setColor(QColor(255, 51, 153))
        self.rubberBandSnap.setIcon(QgsRubberBand.ICON_CROSS)
        self.rubberBandSnap.setIconSize(12)
        self.rubberBandSnap.setWidth(3)
        
        # we need a snapper, so we use the MapCanvas snapper  
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
        super(QgsMapToolEmitPoint, self).deactivate()
        
    def next(self):
        if self.step == 0:
            scaleFactor,found = QgsProject.instance().readEntry(constants.SETTINGS_KEY, 
                    constants.SETTINGS_SCALE_FACTOR, None)
            if not found:
                scaleFactor = str(ScaleDigitizingMode.DEFAULT_SCALE_FACTOR)
            
            _, lineEdit = self.messageBarUtils.showLineEdit(ScaleDigitizingMode.MESSAGE_HEADER, "Draw base point and set scale:", scaleFactor)
            self.lineEditScaleFactor = lineEdit
        elif self.step == 1:
            self.scaleFactor = self.lineEditScaleFactor.text()
            
            if self.layer.selectedFeatureCount() == 0:
                self.messageBarUtils.showYesCancel(ScaleDigitizingMode.MESSAGE_HEADER, "No feature selected in Layer %s. Proceed on full layer?" % self.layer.name(), 
                                                   QgsMessageBar.WARNING, self.doScale)
                return
            
            self.doScale()
         
    def doScale(self):
        _, progress = self.messageBarUtils.showProgress(ScaleDigitizingMode.MESSAGE_HEADER, "Running...", QgsMessageBar.INFO)
        
        try:
            # get the actual vertices from the geometry instead of the snapping
            crsDest = self.layer.crs()
            canvas = self.iface.mapCanvas()
            mapRenderer = canvas.mapSettings()
            crsSrc = mapRenderer.destinationCrs()
            crsTransform = QgsCoordinateTransform(crsSrc, crsDest)
            # arcnode is still in map canvas coordinate => transform to layer coordinate
            self.basePoint = crsTransform.transform(self.basePoint)
            
            try:
                scaleFactor = float(self.scaleFactor)
                # save for next time
                QgsProject.instance().writeEntry(constants.SETTINGS_KEY, 
                    constants.SETTINGS_SCALE_FACTOR, scaleFactor)
            except ValueError:
                scaleFactor = ScaleDigitizingMode.DEFAULT_SCALE_FACTOR
            
            self.iface.mapCanvas().freeze(True)
    
            outFeat = QgsFeature()
            inGeom = QgsGeometry()
    
            current = 0
            features = vectorlayerutils.features(self.layer)
            total = 100.0 / float(len(features))
            for f in features:
                inGeom = f.geometry()
                attrs = f.attributes()
                
                # break into multiple geometries if needed
                if inGeom.isMultipart():
                    geometries = inGeom.asMultiPolyline()
                    outGeom = []
                    
                    for g in geometries:
                        polyline = self.scalePolyline(g, scaleFactor)
                        outGeom.append(polyline)
                        
                    outGeom = QgsGeometry.fromMultiPolyline(outGeom)
                        
                else:
                    polyline = self.scalePolyline(inGeom.asPolyline(), scaleFactor)
                    outGeom = QgsGeometry.fromPolyline(polyline)
                
                outFeat.setAttributes(attrs)
                outFeat.setGeometry(outGeom) 
                self.layer.addFeature(outFeat)
                
                self.layer.deleteFeature(f.id())
                    
                current += 1
                progress.setValue(int(current * total))

        except Exception as e:
            QgsMessageLog.logMessage(repr(e))
            self.messageBarUtils.showMessage(ScaleDigitizingMode.MESSAGE_HEADER, 
                                             "There was an error performing this command. See QGIS Message log for details.", QgsMessageBar.CRITICAL, duration=5)
            self.layer.destroyEditCommand()
            
            return
        finally:
            self.iface.mapCanvas().freeze(False)
            self.iface.mapCanvas().refresh()
        
        # if here: Success!
        self.messageBarUtils.showMessage(ScaleDigitizingMode.MESSAGE_HEADER, "Success", QgsMessageBar.INFO, 5)
        
        self.layer.endEditCommand()
        
        self.iface.mapCanvas().unsetMapTool(self)
            
          
    def scalePolyline(self, polyline, scaleFactor):
        for vertex in polyline:
            # scale
            relBP = QgsPoint(vertex.x() - self.basePoint.x(), vertex.y() - self.basePoint.y())
            vertex.setX(self.basePoint.x() + scaleFactor * relBP.x())
            vertex.setY(self.basePoint.y() + scaleFactor * relBP.y())
            
        return polyline
    
    def enter(self):
        #ignore
        pass
    
    def canvasPressEvent(self, e):
        pass
   
    def canvasReleaseEvent(self, e):
        pos = QPoint(e.pos().x(), e.pos().y())
        result = self.snap(pos)
        if result != []:
            self.basePoint = result[0].snappedVertex
        else:
            self.basePoint = self.toMapCoordinates(e.pos())
    
        self.step = 1
        self.next()
    
    def canvasMoveEvent(self, e):
        pos = QPoint(e.pos().x(), e.pos().y())
        result = self.snap(pos)
        self.rubberBandSnap.reset(QGis.Point)
        if result != []:
            self.rubberBandSnap.addPoint(result[0].snappedVertex, True)
          
    def snap(self, pos):
        if self.digitizingTools.isBackgroundSnapping:
            (_, result) = self.snapper.snapToBackgroundLayers(pos)
        else:
            (_, result) = self.snapper.snapToCurrentLayer(pos, QgsSnapper.SnapToVertex)
        return result