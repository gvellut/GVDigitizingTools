# -*- coding: utf-8 -*-

# Import the PyQt and QGIS libraries
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *

import math

class ParallelConstraintMode(object):
    
    def __init__(self, iface):
        self.iface = iface
        
        self.activeSelection = False
        self.activeConstraint = False
        self.angle = 0
        self.isRelevant = False
        
    def activate(self):
        self.activeSelection = True
        
    def deactivate(self):
        self.activeSelection = False
        self.activeConstraint = False
        self.angle = 0
        self.action.setChecked(False)
        
    def setAction(self, action):
        self.action = action