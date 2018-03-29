# -*- coding: utf-8 -*-
"""
/***************************************************************************
 GVDigitizingTools
                                 A QGIS plugin
 Custom tools for digitizing
                              -------------------
        begin                : 2014-05-21
        copyright            : (C) 2014 by Guilhem Vellut
        email                : guilhem.vellut@gmail.com
 ***************************************************************************/
"""
import os.path

from PyQt4.Qt import qDebug
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *

from settingsdialog import SettingsDialog
from digitizingsetup import DigitizingSetup
from explode import ExplodeCommand
from polygonize import PolygonizeCommand
from intersect import IntersectCommand
from extend import ExtendDigitizingMode
from trim import TrimDigitizingMode
from arc import DrawArcDigitizingMode
from fillet import FilletDigitizingMode
from mirror import MirrorDigitizingMode
from scale import ScaleDigitizingMode
from move import MoveDigitizingMode
from copy import CopyDigitizingMode
from moveMultipleLayers import MoveMultipleLayersDigitizingMode
from copyMultipleLayers import CopyMultipleLayersDigitizingMode
from constrainteventfilter import ConstraintEventFilter, CadPointList
from parallel import ParallelConstraintMode
from split import SplitDigitizingMode
from centerline import CenterlineDigitizingMode
from centerlineadvanced import CenterlineAdvancedDigitizingMode
import constants
import resources_rc


class GVDigitizingTools:

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)

        self.dlgSettings = SettingsDialog()
        
        self.digitizingSetup = DigitizingSetup(self.iface)
        self.currentMode = None
        self.currentLayer = None
        self.isBackgroundSnapping = False
        
        self.initSettings()
        
    def initSettings(self):
        # set default if first time this ie executed
        settings = QSettings()
        method = settings.value(constants.ARC_METHOD,  constants.ARC_METHOD_ANGLE)
        settings.setValue(constants.ARC_METHOD, method)
        angle = settings.value(constants.ARC_ANGLE,  3.0, type=float)
        settings.setValue(constants.ARC_ANGLE, angle)
        numberOfPoints = settings.value(constants.ARC_NUMBEROFPOINTS,  10, type=int)
        settings.setValue(constants.ARC_NUMBEROFPOINTS, numberOfPoints)
        
        enablePreview=settings.value(constants.PREVIEW_ENABLED, True)
        settings.setValue(constants.PREVIEW_ENABLED, enablePreview)
        enablePreviewLimit=settings.value(constants.PREVIEW_LIMIT_ENABLED, False)
        settings.setValue(constants.PREVIEW_LIMIT_ENABLED, enablePreviewLimit)
        maxLimitPreview=settings.value(constants.PREVIEW_LIMIT_MAX, 1000)
        settings.setValue(constants.PREVIEW_LIMIT_MAX, maxLimitPreview)

    def initGui(self):
        self.actions = []
        self.createAction("actionSettings", "icons/iconSettings.png", u"Settings", self.doShowSettings, checkable=False)
        self.createAction("action", "icon.png", u"Digitizing tools", self.doSetupDigitizing)
        self.createAction("actionBackgroundSnapping", "icons/iconSnap.png", u"Snap to background layers", self.doSetupBackgroundSnapping)
        
        self.createAction("actionDrawArc", "icons/iconDrawArc.png", u"Add arc", self.doDrawArc, "Alt+Ctrl+S")
        self.createAction("actionExtend", "icons/iconExtend.png", u"Extend", self.doExtend, "Alt+Ctrl+E")
        self.createAction("actionFillet", "icons/iconFillet.png", u"Fillet", self.doFillet, "Alt+Ctrl+F")
        self.createAction("actionTrim", "icons/iconTrim.png", u"Trim", self.doTrim, "Alt+Ctrl+C")
        self.createAction("actionMirror", "icons/iconMirror.png", u"Mirror", self.doMirror, "Alt+Ctrl+W")
        self.createAction("actionScale", "icons/iconScale.png", u"Scale", self.doScale, "Alt+Ctrl+Z")
        self.createAction("actionMove", "icons/iconMove.png", u"Move", self.doMove, "Alt+Ctrl+D")
        self.createAction("actionCopy", "icons/iconCopy.png", u"Copy", self.doCopy, "Alt+Ctrl+X")
        self.createAction("actionMoveMultipleLayers", "icons/iconMoveMultipleLayers.png", u"Move from multiple layers", self.doMoveMultipleLayers, "Alt+Ctrl+Q")
        self.createAction("actionCopyMultipleLayers", "icons/iconCopyMultipleLayers.png", u"Copy from multiple layers", self.doCopyMultipleLayers, "Alt+Ctrl+R")
        self.createAction("actionParallel", "icons/iconParallel.png", u"Parallel", self.doParallel, "Alt+Ctrl+P")
        self.createAction("actionSplit", "icons/iconSplit.png", u"Split", self.doSplit, "Alt+Ctrl+H")
        self.createAction("actionCenterline", "icons/iconCenterline.png", u"Centerline", self.doCenterline, "Alt+Ctrl+J")
        self.createAction("actionCenterlineAdvanced", "icons/iconCenterlineAdvanced.png", u"Centerline Advanced", self.doCenterlineAdvanced, "Alt+Ctrl+K")
        
        self.createAction("actionPolygonize", "icons/iconPolygonize.png", u"Polygonize", self.doPolygonize, checkable=False)
        self.createAction("actionIntersect", "icons/iconIntersect.png", u"Create node at intersections", self.doIntersect, checkable=False)
        self.createAction("actionExplode", "icons/iconExplode.png", u"Explode multipart to single parts", self.doExplode, checkable=False)

        # Add toolbar button and menu item
        self.iface.addPluginToMenu(u"&GV Digitizing Tools", self.actionSettings)
        
        self.toolbar = self.iface.addToolBar("GV Digitizing Tools")
        self.toolbar.addAction(self.action)
        self.toolbar.addAction(self.actionBackgroundSnapping)
        self.toolbar.addSeparator()
        self.addActionGroup([self.actionDrawArc, self.actionExtend, self.actionFillet,
                   self.actionTrim, self.actionMirror, self.actionScale, self.actionParallel, 
                   self.actionSplit, 
                   self.actionCenterline, self.actionCenterlineAdvanced])
        self.toolbar.addSeparator()
        self.addActionGroup([self.actionMove, self.actionCopy,
                   self.actionMoveMultipleLayers, self.actionCopyMultipleLayers])
        self.toolbar.addSeparator()
        self.addActionGroup([self.actionPolygonize, self.actionIntersect, self.actionExplode])
        
        self.ignoreActions = set([self.action, self.actionSettings, self.actionBackgroundSnapping, 
                                  self.actionMoveMultipleLayers, self.actionCopyMultipleLayers, self.actionParallel])
        self.action.setEnabled(True)
        self.actionMoveMultipleLayers.setEnabled(True)
        self.actionCopyMultipleLayers.setEnabled(True)
        self.actionParallel.setEnabled(False)
        self.actionBackgroundSnapping.setEnabled(True)
            
        self.extendMode = ExtendDigitizingMode(self.iface)
        self.extendMode.setAction(self.actionExtend) 
        self.trimMode = TrimDigitizingMode(self.iface)
        self.trimMode.setAction(self.actionTrim)
        self.drawArcMode = DrawArcDigitizingMode(self.iface)
        self.drawArcMode.setAction(self.actionDrawArc)
        self.filletMode = FilletDigitizingMode(self.iface)
        self.filletMode.setAction(self.actionFillet)
        self.mirrorMode = MirrorDigitizingMode(self.iface, self)
        self.mirrorMode.setAction(self.actionMirror)
        self.scaleMode = ScaleDigitizingMode(self.iface, self)
        self.scaleMode.setAction(self.actionScale)
        self.moveMode = MoveDigitizingMode(self.iface, self)
        self.moveMode.setAction(self.actionMove)
        self.copyMode = CopyDigitizingMode(self.iface, self)
        self.copyMode.setAction(self.actionCopy)
        self.moveMultipleLayersMode = MoveMultipleLayersDigitizingMode(self.iface, self)
        self.moveMultipleLayersMode.setAction(self.actionMoveMultipleLayers)
        self.copyMultipleLayersMode = CopyMultipleLayersDigitizingMode(self.iface, self)
        self.copyMultipleLayersMode.setAction(self.actionCopyMultipleLayers)
        self.parallelConstraintMode = ParallelConstraintMode(self.iface)
        self.parallelConstraintMode.setAction(self.actionParallel)
        self.splitMode=SplitDigitizingMode(self.iface)
        self.splitMode.setAction(self.actionSplit)
        self.centerlineMode=CenterlineDigitizingMode(self.iface)
        self.centerlineMode.setAction(self.actionCenterline)
        self.centerlineAdvancedMode=CenterlineAdvancedDigitizingMode(self.iface)
        self.centerlineAdvancedMode.setAction(self.actionCenterlineAdvanced)
        
        self.explodeCommand = ExplodeCommand(self.iface)
        self.polygonizeCommand = PolygonizeCommand(self.iface) 
        self.intersectCommand = IntersectCommand(self.iface)
        
        self.cadPointList = CadPointList(self.checkIsParallelEnabled)
        self.eventFilter = ConstraintEventFilter(self.iface, self, self.cadPointList)
        # to track the mouse for mouseMoveEvents to happen
        self.iface.mapCanvas().viewport().setMouseTracking(True)
        # to get the mouse events
        self.iface.mapCanvas().viewport().installEventFilter( self.eventFilter )
        
        self.iface.legendInterface().currentLayerChanged.connect( self.currentLayerChanged)
        self.currentLayer = self.iface.legendInterface().currentLayer()
        if self.currentLayer and self.currentLayer.type() == QgsMapLayer.VectorLayer:
            self.currentLayer.editingStopped.connect(self.editingStopped)
            self.currentLayer.editingStarted.connect(self.editingStarted)
            self.currentLayer.selectionChanged.connect(self.selectionChanged)
        self.iface.mapCanvas().mapToolSet.connect(self.maptoolChanged)
        
        self.maptoolChanged()
        self.checkCurrentLayerIsEditableLineLayer()
        self.checkIsMultipleMoveOrCopyEnabled()
        self.checkIsParallelEnabled()
        

    def unload(self):
        # Remove the plugin menu item and icon
        self.iface.removePluginMenu(u"&GV Digitizing Tools", self.actionSettings)
        
        self.iface.legendInterface().currentLayerChanged.disconnect( self.currentLayerChanged)
        self.currentLayer = self.iface.legendInterface().currentLayer()
        if self.currentLayer:
            try: self.currentLayer.editingStarted.disconnect(self.editingStarted)
            except Exception: pass 
            try: self.currentLayer.editingStopped.disconnect(self.editingStopped)
            except Exception: pass 
            try:self.currentLayer.selectionChanged.disconnect(self.selectionChanged)
            except:pass
        self.iface.mapCanvas().mapToolSet.disconnect(self.maptoolChanged)
        
        self.iface.mapCanvas().viewport().setMouseTracking(False)
        self.eventFilter.close()
        self.iface.mapCanvas().viewport().removeEventFilter( self.eventFilter )
        
        del self.toolbar
        
    def createAction(self, name, icon, tip, callback, shortcut = None, checkable=True):
        
        action = QAction(
            QIcon(":/plugins/gvdigitizingtools/" + icon),
            tip, self.iface.mainWindow())
        # connect the action to the run method
        action.triggered.connect(callback)
        action.setCheckable(checkable)
        
        if shortcut:
            action.setShortcut(shortcut)
            
        self.__dict__[name] = action
        self.actions.append(action)
        
    def addActionGroup(self, actions):
        for action in actions:
            self.toolbar.addAction(action)
        
    def currentLayerChanged(self):
        # first cleanup events for previous layer
        if self.currentLayer:
            try: self.currentLayer.editingStarted.disconnect(self.editingStarted)
            except Exception: pass 
            try: self.currentLayer.editingStopped.disconnect(self.editingStopped)
            except Exception: pass 
            try:self.currentLayer.selectionChanged.disconnect(self.selectionChanged)
            except:pass
        self.currentLayer = self.iface.legendInterface().currentLayer()
        if self.currentLayer and self.currentLayer.type() == QgsMapLayer.VectorLayer:
            self.currentLayer.editingStopped.connect(self.editingStopped)
            self.currentLayer.editingStarted.connect(self.editingStarted)
            self.currentLayer.selectionChanged.connect(self.selectionChanged)
        
        self.checkCurrentLayerIsEditableLineLayer()
        self.checkIsParallelEnabled()
        
        # selectedLayers not yet updated and no event for this (have to use 
        # currentLAyer change event)
        # get stuck when going from multiple to one selection
        QTimer.singleShot(1, self.checkIsMultipleMoveOrCopyEnabled)
        
    def editingStarted(self):
        self.checkCurrentLayerIsEditableLineLayer()
        self.checkIsParallelEnabled()
        
    def editingStopped(self):
        self.checkCurrentLayerIsEditableLineLayer()
        self.checkIsParallelEnabled()
        
    def selectionChanged(self):
        self.checkIsMultipleMoveOrCopyEnabled()
        
    def maptoolChanged(self):
        self.parallelConstraintMode.isRelevant = (self.iface.mapCanvas().mapTool() is not None and 
                                                  self.iface.mapCanvas().mapTool().isEditTool())
        
    def checkCurrentLayerIsEditableLineLayer(self):
        if self.currentLayer and self.currentLayer.type() == QgsMapLayer.VectorLayer and self.currentLayer.geometryType() == QGis.Line and self.currentLayer.isEditable():
            for action in self.actions:
                # special processing for MoveMultipleLayers
                if action not in self.ignoreActions:
                    action.setEnabled(True)
                
            if self.currentMode and self.currentMode != self.moveMultipleLayersMode:
                self.currentMode.reset()
                self.currentMode.setLayer(self.currentLayer)
            
        else:   
            for action in self.actions:
                if action not in self.ignoreActions:
                    action.setEnabled(False)
                
            if self.currentMode and self.currentMode != self.moveMultipleLayersMode:
                self.currentMode.reset()
                self.iface.mapCanvas().unsetMapTool(self.currentMode)
                self.currentMode = None

    def checkIsParallelEnabled(self):
        if (self.currentLayer and self.currentLayer.type() == QgsMapLayer.VectorLayer
                and self.currentLayer.geometryType() == QGis.Line and self.currentLayer.isEditable()
                and len(self.cadPointList)>1 and self.digitizingSetup.enableEventFilter):
            self.actionParallel.setEnabled(True)
        else:
            self.actionParallel.setEnabled(False)

    def checkIsMultipleMoveOrCopyEnabled(self):
        layers = self.iface.legendInterface().selectedLayers()
        for layer in layers:
            if layer.type() == QgsMapLayer.VectorLayer:
                if layer.selectedFeatureCount() > 0:
                    self.actionMoveMultipleLayers.setEnabled(True)
                    self.actionCopyMultipleLayers.setEnabled(True)
                    return
        self.moveMultipleLayersMode.reset()
        self.copyMultipleLayersMode.reset()
        self.actionMoveMultipleLayers.setChecked(False)
        self.actionMoveMultipleLayers.setEnabled(False)
        self.actionCopyMultipleLayers.setChecked(False)
        self.actionCopyMultipleLayers.setEnabled(False)
                
    def setupMode(self):
        layer = self.iface.legendInterface().currentLayer()
        self.currentMode.setLayer(layer)
        self.iface.mapCanvas().setMapTool(self.currentMode)
        
        self.currentMode.reset()
        self.currentMode.next()

    def doSetupDigitizing(self):
        if self.action.isChecked():
            self.digitizingSetup.activate()
            self.checkIsParallelEnabled()
        else:
            self.digitizingSetup.deactivate()
            self.checkIsParallelEnabled()
            
    def doSetupBackgroundSnapping(self):
        self.isBackgroundSnapping = self.actionBackgroundSnapping.isChecked()
        
    def doShowSettings(self):
        self.dlgSettings.clear()
        self.dlgSettings.show()
        result = self.dlgSettings.exec_()
    
    def doDrawArc(self):
        self.currentMode = self.drawArcMode
        self.setupMode()
    
    def doExtend(self):
        self.currentMode = self.extendMode
        self.setupMode()
    
    def doFillet(self):
        self.currentMode = self.filletMode
        self.setupMode()
    
    def doTrim(self):
        self.currentMode = self.trimMode
        self.setupMode()
    
    def doMirror(self):
        self.currentMode = self.mirrorMode
        self.setupMode()
    
    def doScale(self):
        self.currentMode = self.scaleMode
        self.setupMode()
        
    def doMove(self):
        self.currentMode = self.moveMode
        self.setupMode()
        
    def doCopy(self):
        self.currentMode = self.copyMode
        self.setupMode()
        
    def doMoveMultipleLayers(self):
        self.currentMode = self.moveMultipleLayersMode
        self.setupMode()
       
    def doCopyMultipleLayers(self):
        self.currentMode = self.copyMultipleLayersMode
        self.setupMode()
        
    def doParallel(self):
        if self.actionParallel.isChecked():
            self.parallelConstraintMode.activate()
        else:
            self.parallelConstraintMode.deactivate()
    
    def doSplit(self):
        self.currentMode = self.splitMode
        self.setupMode()
    
    def doCenterline(self):
        self.currentMode=self.centerlineMode
        self.setupMode()
        
    def doCenterlineAdvanced(self):
        self.currentMode=self.centerlineAdvancedMode
        self.setupMode()
            
    def doPolygonize(self):
        self.polygonizeCommand.run()
    
    def doIntersect(self):
        self.intersectCommand.run()
    
    def doExplode(self):
        self.explodeCommand.run()