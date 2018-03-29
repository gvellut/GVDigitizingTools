# -*- coding: utf-8 -*-

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from qgis.core import *
from qgis.gui import *

class ExtendUtils:
    
    def __init__(self, iface):
        self.iface = iface
        self.canvas = self.iface.mapCanvas()
        
        
    # Use following algorithm:
    # A = y2-y1
    # B = x1-x2
    # C = A*x1+B*y1    
    #
    # det = A1*B2 - A2*B1
    # X = (B2*C1 - B1*C2) / det
    # Y = (A1*C2 - A2*C1) / det
        
    def intersectionPoint(self, p11, p12, p21, p22 ):
        a1 = p12.y() - p11.y()
        b1 = p11.x() - p12.x()
        c1 = a1*p11.x() + b1*p11.y()
        
        a2 = p22.y() - p21.y()
        b2 = p21.x() - p22.x()
        c2 = a2*p21.x() + b2*p21.y()
        
        det = a1*b2 - a2*b1
        
        if det == 0:
            return None
        else:
            x = (b2*c1 - b1*c2) / det
            y = (a1*c2 - a2*c1) / det
            p = QgsPoint(x, y)
            return p
        
    def vertexIndexToMove(self, bvExtend, avExtend, segmentExtend, point, mustExtend = True):   
        g1 = QgsGeometry.fromPoint(bvExtend)
        g2 = QgsGeometry.fromPoint(avExtend)
        p = QgsGeometry.fromPoint(point)
        
        d1 = g1.distance(p)
        d2 = g2.distance(p)
        d = g1.distance(g2)
        
        if d1 > d2:
            # move g2 to position p. leave g1 where it is.
            # check that distance g1 to p is greater than distance g1 to g2 (or it is not an extend)
            if mustExtend and d > d1:
                return None
            return segmentExtend.afterVertexNr
        else:
            if mustExtend and d > d2:
                return None
            return segmentExtend.beforeVertexNr
    
